"""
Centralized trading execution logic.
Handles order placement, leverage setting, and margin calculations.
"""

from typing import Optional, Dict, Any
import time
import os
import uuid
from datetime import datetime
from core.logger import get_logger
from api.rest_client import DeltaRestClient
from notifications.manager import NotificationManager
from core.firestore_client import journal_trade  # For trade journaling to Firestore

logger = get_logger(__name__)

def _parse_position_timestamp_us(created_at) -> Optional[int]:
    """
    Convert a position's created_at value to microseconds epoch.

    Handles seconds (int/float) and ISO 8601 strings from the Delta API.

    Args:
        created_at: Timestamp as int/float seconds, milliseconds, or ISO string

    Returns:
        Microseconds epoch int, or None if parsing fails
    """
    if created_at is None:
        return None
    try:
        if isinstance(created_at, (int, float)):
            ts = float(created_at)
            if ts > 1e15:   # already microseconds
                return int(ts)
            if ts > 1e12:   # milliseconds
                return int(ts * 1_000)
            return int(ts * 1_000_000)  # seconds → microseconds
        # ISO string (e.g. "2024-03-14T10:30:00Z")
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        return int(dt.timestamp() * 1_000_000)
    except Exception:
        return None


def calculate_position_size(
    target_margin: float,
    price: float,
    leverage: int,
    contract_value: float,
    enable_partial_tp: bool = False,
    sizing_type: str = "margin",
    atr: Optional[float] = None,
    atr_multiplier: float = 2.0,
    atr_margin_cap_multiplier: float = 1.5
) -> int:
    """
    Calculate position size dynamically based on target margin or ATR volatility.
    
    Args:
        target_margin: Target margin to use (e.g., 40 USD)
        price: Current market price
        leverage: Leverage to apply
        contract_value: Contract value from product info
        enable_partial_tp: Whether partial take-profit is enabled
        sizing_type: "margin" or "atr"
        atr: Average True Range value (required for "atr" sizing)
        atr_multiplier: Multiplier for ATR sizing (Risk = Target Margin / (ATR * Multiplier))
        atr_margin_cap_multiplier: Safety cap multiplier (Max Margin = Target Margin * Cap)
        
    Returns:
        Calculated position size (integer number of contracts)
        
    Logic (Margin):
        1. Calculate base size: (target_margin * leverage) / (price * contract_value)
    
    Logic (ATR):
        1. Calculate base size: target_margin / (atr * atr_multiplier * contract_value)
        
    Common:
        2. Round to integer
        3. If enable_partial_tp is True and size is odd, round to nearest even number
        4. Validate final size doesn't exceed target margin (for margin mode)
        5. Return size (minimum 2 if partial TP enabled, minimum 1 otherwise)
    """
    try:
        # Calculate base position size based on method
        if sizing_type.lower() == "atr" and atr is not None and atr > 0:
            # Formula: Target Margin / (ATR * Multiplier * contract_value)
            # This allocates 'target_margin' of capital for every (ATR * Multiplier) move in price
            base_size = target_margin / (atr * atr_multiplier * contract_value)
            calc_mode = f"ATR (ATR={atr:.4f}, Mult={atr_multiplier})"
        else:
            # Standard Formula: (target_margin * leverage) / (price * contract_value)
            base_size = (target_margin * leverage) / (price * contract_value)
            calc_mode = "MARGIN"
        
        # Round to integer
        position_size = int(base_size)
        
        # If partial TP is enabled, ensure even number for clean 50% exits
        if enable_partial_tp:
            if position_size % 2 != 0:
                # Round to nearest even number
                # If size is odd, add 1 to make it even
                position_size += 1
            
            # Ensure minimum of 2 contracts when partial TP is enabled
            if position_size < 2:
                position_size = 2
                logger.warning(
                    f"Position size too small for partial TP. Setting to minimum: {position_size} contracts. "
                    f"Target margin: ${target_margin}, Price: ${price}, Leverage: {leverage}x"
                )
        else:
            # Ensure minimum of 1 contract
            if position_size < 1:
                position_size = 1
        
        # Validate that the final size doesn't significantly exceed target margin (for Margin mode)
        # Apply ATR Safety Cap if specified and using ATR mode
        if sizing_type.lower() == "atr" and atr_margin_cap_multiplier is not None:
            max_allowed_margin = target_margin * atr_margin_cap_multiplier
            actual_margin = (position_size * price * contract_value) / leverage
            
            if actual_margin > max_allowed_margin:
                old_size = position_size
                # Max Size = (Target Margin * Cap * Leverage) / (Price * Contract Value)
                position_size = int((max_allowed_margin * leverage) / (price * contract_value))
                
                # Ensure even handle if partial TP enabled
                if enable_partial_tp:
                    if position_size % 2 != 0: position_size -= 1
                    if position_size < 2: position_size = 2
                else:
                    if position_size < 1: position_size = 1
                
                new_margin = (position_size * price * contract_value) / leverage
                logger.warning(
                    f"ATR Safety Cap triggered for {calc_mode}: "
                    f"Actual Margin ${actual_margin:.2f} > Cap ${max_allowed_margin:.2f}. "
                    f"Capping size from {old_size} to {position_size} (New Margin: ${new_margin:.2f})"
                )
        
        actual_margin = (position_size * price * contract_value) / leverage
        
        # Log calculation details
        logger.info(
            f"Position size calculation ({calc_mode}): "
            f"Target Margin=${target_margin:.2f}, Price=${price:.2f}, "
            f"Leverage={leverage}x, Contract Value={contract_value}, "
            f"Partial TP Enabled={enable_partial_tp} → "
            f"Position Size={position_size} contracts (Actual Margin=${actual_margin:.2f})"
        )
        
        return position_size
        
    except Exception as e:
        logger.error(f"Error calculating position size: {e}")
        # Return safe default based on partial TP setting
        return 2 if enable_partial_tp else 1

def get_trade_config(symbol: str, sizing_config: Optional[Dict[str, Any]] = None):
    """
    Get trade configuration for a symbol from environment variables and optional sizing_config.
    
    Args:
        symbol: Trading symbol (e.g., 'PIPPINUSD')
        sizing_config: Optional dictionary of sizing flags (e.g. from multi_coin config)
    
    Returns:
        dict: {
            "order_size": int,
            "leverage": int,
            "enabled": bool,
            "base_asset": str,
            "target_margin": float,
            "sizing_type": str,
            "atr_multiplier": float,
            "atr_margin_cap_multiplier": float
        }
    """
    # 1. Determine Base Asset
    base_asset = symbol.upper().replace("USD", "").replace("USDT", "").replace("-", "").replace("/", "").replace("_", "")
    
    # 2. Defaults
    order_size = 1  
    leverage = 5
    target_margin = 40.0  # Default target margin in USD
    
    # Position Sizing Type (margin or atr)
    from core.config import get_config
    config = get_config()
    sizing_type = config.risk_management.position_sizing_type if hasattr(config, 'risk_management') else "margin"
    atr_multiplier = config.risk_management.atr_margin_multiplier if hasattr(config, 'risk_management') else 2.0
    atr_margin_cap_multiplier = config.risk_management.atr_margin_cap_multiplier if hasattr(config, 'risk_management') else 1.5

    # 3. Load overrides from Environment (Priority 2 / Fallback)
    try:
        leverage = int(os.getenv(f"LEVERAGE_{base_asset}", os.getenv("LEVERAGE", str(leverage))))
        target_margin = float(os.getenv(f"TARGET_MARGIN_{base_asset}", str(target_margin)))
        
        # Legacy env support for sizing flags (Priority 3)
        sizing_type = os.getenv(f"POSITION_SIZING_TYPE_{base_asset}", sizing_type).lower()
        atr_multiplier = float(os.getenv(f"ATR_MARGIN_MULTIPLIER_{base_asset}", str(atr_multiplier)))
        atr_margin_cap_multiplier = float(os.getenv(f"ATR_MARGIN_CAP_MULTIPLIER_{base_asset}", str(atr_margin_cap_multiplier)))
    except ValueError:
        logger.warning(f"Invalid environment configuration for {base_asset}, using current values.")

    # 4. Load overrides from sizing_config (Priority 1)
    if sizing_config:
        if "position_sizing_type" in sizing_config:
            sizing_type = sizing_config["position_sizing_type"].lower()
        if "atr_margin_multiplier" in sizing_config:
            atr_multiplier = float(sizing_config["atr_margin_multiplier"])
        if "leverage" in sizing_config:
            leverage = int(sizing_config["leverage"])
        if "target_margin" in sizing_config:
            target_margin = float(sizing_config["target_margin"])
        if "atr_margin_cap_multiplier" in sizing_config:
            atr_margin_cap_multiplier = float(sizing_config["atr_margin_cap_multiplier"])
        logger.debug(f"Loaded config overrides for {symbol.upper()} from multi-coin settings")

    # 5. Check Enable Flag
    env_var_key = f"ENABLE_ORDER_PLACEMENT_{base_asset}"
    enable_orders = os.getenv(env_var_key, "false").lower() == "true"
    
    return {
        "order_size": order_size,  # Deprecated: kept for backwards compatibility
        "leverage": leverage,
        "enabled": enable_orders,
        "base_asset": base_asset,
        "target_margin": target_margin,  # New: configurable target margin
        "sizing_type": sizing_type,
        "atr_multiplier": atr_multiplier,
        "atr_margin_cap_multiplier": atr_margin_cap_multiplier
    }

def execute_strategy_signal(
    client: DeltaRestClient, 
    symbol: str, 
    action: str, 
    market_price: float, 
    reason: str, 
    notifier: NotificationManager, 
    strategy_name: str,
    enable_partial_tp: bool = False,
    timeframe: str = "1h",
    atr: Optional[float] = None,
    sizing_config: Optional[Dict[str, Any]] = None
):
    """
    Execute a strategy signal by placing orders and sending notifications.
    """
    # 1. Get symbol configuration
    trade_config = get_trade_config(symbol, sizing_config=sizing_config)
    
    try:
        # 1. Resolve Product ID
        products = client.get_products()
        product = next((p for p in products if p['symbol'] == symbol), None)
        
        if not product:
            logger.error(f"Could not find product for symbol {symbol}")
            return
            
        product_id = product['id']
        contract_value = float(product.get('contract_value', 1.0)) # Usually 0.001 BTC or similar
        
        # 2. Get Configuration
        order_size = trade_config['order_size']  # Will be overridden for entries with dynamic sizing
        leverage = trade_config['leverage']
        enable_orders = trade_config['enabled']
        base_asset = trade_config['base_asset']
        target_margin = trade_config['target_margin']
        sizing_type = trade_config.get('sizing_type', 'margin')
        atr_multiplier = trade_config.get('atr_multiplier', 2.0)
        atr_margin_cap_multiplier = trade_config.get('atr_margin_cap_multiplier', 1.5)
        
        side = None
        is_entry = False
        lot_size = None  # Will be set for notifications
        active_position = None  # Store position data for PnL/fees extraction
        
        # Handle entry orders with dynamic position sizing
        if action == "ENTRY_LONG":
            side = "buy"
            is_entry = True
            
            # Use dynamic position sizing for entries
            try:
                # Get current market price for accurate calculation
                ticker = client.get_ticker(symbol)
                current_price = float(ticker.get('close', price))
                logger.info(f"Fetched current market price for position sizing: ${current_price:.2f}")
                
                # Calculate dynamic position size
                order_size = calculate_position_size(
                    target_margin=target_margin,
                    price=current_price,
                    leverage=leverage,
                    contract_value=contract_value,
                    enable_partial_tp=enable_partial_tp,
                    sizing_type=sizing_type,
                    atr=atr,
                    atr_multiplier=atr_multiplier,
                    atr_margin_cap_multiplier=atr_margin_cap_multiplier
                )
                lot_size = order_size  # Store for notification
                logger.info(f"Calculated position size for ENTRY_LONG: {order_size} contracts (Sizing: {sizing_type})")
            except Exception as e:
                logger.error(f"Failed to calculate dynamic position size: {e}. Using default.")
                order_size = 2 if enable_partial_tp else 1
                lot_size = order_size
                
        elif action == "ENTRY_SHORT":
            side = "sell"
            is_entry = True
            
            # Use dynamic position sizing for entries
            try:
                # Get current market price for accurate calculation
                ticker = client.get_ticker(symbol)
                current_price = float(ticker.get('close', price))
                logger.info(f"Fetched current market price for position sizing: ${current_price:.2f}")
                
                # Calculate dynamic position size
                order_size = calculate_position_size(
                    target_margin=target_margin,
                    price=current_price,
                    leverage=leverage,
                    contract_value=contract_value,
                    enable_partial_tp=enable_partial_tp,
                    sizing_type=sizing_type,
                    atr=atr,
                    atr_multiplier=atr_multiplier,
                    atr_margin_cap_multiplier=atr_margin_cap_multiplier
                )
                lot_size = order_size  # Store for notification
                logger.info(f"Calculated position size for ENTRY_SHORT: {order_size} contracts (Sizing: {sizing_type})")
            except Exception as e:
                logger.error(f"Failed to calculate dynamic position size: {e}. Using default.")
                order_size = 2 if enable_partial_tp else 1
                lot_size = order_size
        elif action == "EXIT_LONG" or action == "EXIT_SHORT":
            # For final exits, fetch actual position size from exchange
            # to avoid selling more than what's actually held (e.g., after partial exits)
            side = "sell" if action == "EXIT_LONG" else "buy"
            
            try:
                current_positions = client.get_positions(product_id=product_id)
                active_position = next((p for p in current_positions if float(p.get('size', 0)) != 0), None)
                if active_position:
                    current_size = abs(float(active_position['size']))
                    order_size = int(current_size)
                    lot_size = order_size  # Store for notification
                    logger.info(f"Final Exit: Closing {order_size} lots (actual position size)")
                    logger.info(f"Position data for PnL: {active_position}")
                else:
                    logger.warning("No active position found for final exit. Sending ALERT ONLY.")
                    enable_orders = False
                    reason += " [NO POSITION]"
            except Exception as e:
                logger.error(f"Failed to fetch position for final exit: {e}")
                # Don't place order if we can't verify position
                enable_orders = False
                reason += " [POSITION FETCH FAILED]"
        elif action == "EXIT_LONG_PARTIAL" or action == "EXIT_SHORT_PARTIAL":
            # Determine side based on closing direction
            # If EXIT_LONG_PARTIAL (Closing Long) -> CELL (sell)
            # If EXIT_SHORT_PARTIAL (Closing Short) -> BUY
            side = "sell" if action == "EXIT_LONG_PARTIAL" else "buy"

            # Fetch current position to calculate 50%
            try:
                current_positions = client.get_positions(product_id=product_id)
                active_position = next((p for p in current_positions if float(p.get('size', 0)) != 0), None)
                if active_position:
                    current_size = abs(float(active_position['size']))
                    # Calculate 50% size (integer)
                    partial_size = int(current_size * 0.5)
                    
                    if partial_size > 0:
                        order_size = partial_size
                        lot_size = order_size  # Store for notification
                        logger.info(f"Partial Exit: Closing {order_size} lots (50% of {current_size})")
                    else:
                        logger.warning(f"Position size {current_size} too small to partial. Sending ALERT ONLY.")
                        enable_orders = False
                        reason += " [SIZE TOO SMALL]"
                else:
                    logger.warning("No active position found for partial exit. Sending ALERT ONLY.")
                    enable_orders = False
                    reason += " [NO POSITION]"
            except Exception as e:
                logger.error(f"Failed to fetch position for partial exit: {e}")
                enable_orders = False
        elif action == "PARTIAL_EXIT":
            # Generic PARTIAL_EXIT action (used by Donchian and RSI-200-EMA strategies)
            # Determine side from current exchange position
            try:
                current_positions = client.get_positions(product_id=product_id)
                active_position = next((p for p in current_positions if float(p.get('size', 0)) != 0), None)
                if active_position:
                    current_size = float(active_position['size'])
                    # Positive size = LONG position → sell to close partial
                    # Negative size = SHORT position → buy to close partial
                    side = "sell" if current_size > 0 else "buy"
                    
                    # Calculate 50% of absolute position size
                    partial_size = int(abs(current_size) * 0.5)
                    
                    if partial_size > 0:
                        order_size = partial_size
                        lot_size = order_size  # Store for notification
                        logger.info(f"Partial Exit: Closing {order_size} lots (50% of {abs(current_size)}) - Direction: {'LONG' if current_size > 0 else 'SHORT'}")
                    else:
                        logger.warning(f"Position size {abs(current_size)} too small to partial. Sending ALERT ONLY.")
                        enable_orders = False
                        reason += " [SIZE TOO SMALL]"
                else:
                    logger.warning("No active position found for partial exit. Sending ALERT ONLY.")
                    enable_orders = False
                    reason += " [NO POSITION]"
            except Exception as e:
                logger.error(f"Failed to fetch position for partial exit: {e}")
                enable_orders = False
        elif action == "MILESTONE_EXIT":
            # Profit milestone exit — dynamic exit percentage parsed from reason string
            import re
            exit_pct_match = re.search(r"exit_pct=([0-9.]+)", reason)
            exit_pct = float(exit_pct_match.group(1)) if exit_pct_match else 0.30
            try:
                current_positions = client.get_positions(product_id=product_id)
                active_position = next((p for p in current_positions if float(p.get('size', 0)) != 0), None)
                if active_position:
                    current_size = float(active_position['size'])
                    side = "sell" if current_size > 0 else "buy"
                    milestone_size = int(abs(current_size) * exit_pct)
                    if milestone_size > 0:
                        order_size = milestone_size
                        lot_size = order_size
                        logger.info(
                            f"Milestone Exit: Closing {order_size} lots"
                            f" ({exit_pct:.0%} of {abs(current_size)})"
                            f" - Direction: {'LONG' if current_size > 0 else 'SHORT'}"
                        )
                    else:
                        logger.warning(f"Position size {abs(current_size)} too small for milestone exit. Sending ALERT ONLY.")
                        enable_orders = False
                        reason += " [SIZE TOO SMALL]"
                else:
                    logger.warning("No active position found for milestone exit. Sending ALERT ONLY.")
                    enable_orders = False
                    reason += " [NO POSITION]"
            except Exception as e:
                logger.error(f"Failed to fetch position for milestone exit: {e}")
                enable_orders = False

        if not side:
            logger.warning(f"Unknown action: {action}")
            return

        # Prevent duplicate entries if position already exists
        if is_entry:
            try:
                current_positions = client.get_positions(product_id=product_id)
                # Filter for non-zero size just in case
                active_position = next((p for p in current_positions if float(p.get('size', 0)) != 0), None)
                
                if active_position:
                    logger.warning(f"Skipping {action} for {symbol}: Active position already exists (Size: {active_position.get('size')}).")
                    return
            except Exception as e:
                logger.error(f"Failed to check existing positions for {symbol}: {e}")
                return

        if not enable_orders:
            logger.warning(f"Order placement disabled for {symbol} (Checked ENABLE_ORDER_PLACEMENT_{base_asset}). Action: {action}")
            reason += " [DISABLED]"

        # 4. Set Leverage (Only on Entry)
        # Only set leverage if orders are enabled, or maybe we still want to set it?
        # Let's skip it if orders are disabled to be safe/quiet
        if is_entry and mode != "paper" and enable_orders:
            try:
                client.set_leverage(product_id, str(leverage))
                logger.info(f"Set leverage to {leverage}x for {symbol}")
            except Exception as e:
                logger.error(f"Failed to set leverage: {e}")
                # Continue anyway, might already be set
        
        # 5. Place Order (Market)
        order = None  # Initialize to prevent UnboundLocalError when orders are disabled
        
        if mode == "paper":
            logger.info(f"[PAPER] Simulating {side.upper()} order for {order_size} contract(s) of {symbol}")
            order = {"id": "PAPER_ORDER_ID"}
            margin_used = 0.0
            remaining_margin = 0.0
            # Estimate margin for dashboard consistency
            notional_value = price * order_size * contract_value
            margin_used = notional_value / leverage
        else:
            # Initialize execution_price for live mode
            execution_price = None
            
            # 7. Execute Order if Enabled
            if enable_orders:
                logger.info(f"Placing {side.upper()} order for {order_size} contract(s) of {symbol}")
                try:
                    order = client.place_order(
                        product_id=product_id,
                        size=order_size,
                        side=side,
                        order_type="market_order"
                    )
                    logger.info(f"Order placed successfully: {order.get('id')}")
                    
                    # Fetch actual position from exchange to get precise entry price
                    if is_entry:
                        time.sleep(1.0) # Wait for matching engine
                        try:
                            logger.info("Fetching actual position from exchange for accurate entry price...")
                            pos_check = client.get_positions(product_id=product_id)
                            # Handle list vs dict response just in case, though get_positions usually returns list
                            if isinstance(pos_check, dict):
                                pos_check = [pos_check]
                                
                            real_pos = next((p for p in pos_check if float(p.get('size', 0)) != 0 and p.get('product_id') == product_id), None)
                            
                            if real_pos:
                                real_entry = float(real_pos.get('entry_price', 0))
                                if real_entry > 0:
                                    execution_price = real_entry
                                    price = real_entry # IMPORTANT: Update price for notification
                                    logger.info(f"Updated Execution Price from Exchange Position: {execution_price}")
                        except Exception as ep:
                            logger.warning(f"Failed to fetch real position after order: {ep}")
                    
                    # Attempt to get fill price from response
                    # Attempt to get fill price from response if not already set by position fetch
                    if not execution_price and order.get('avg_fill_price'):
                        execution_price = float(order['avg_fill_price'])
                        logger.info(f"Execution Price from response: {execution_price}")
                    else:
                        # Fallback: Fetch order details? Or just leave as None and use candle close
                        # Usually market orders return fills immediately or we wait a split second
                        pass

                except Exception as e:
                    logger.error(f"Failed to place order: {e}")
                    notifier.send_error(f"Order Failed: {symbol}", str(e))
                    return {"success": False, "error": str(e)}

                # --- EXCHANGE BRACKET STOP-LOSS (Removed) ---
                # Bracket stop-loss placement has been disabled as per user request.
            else:
                logger.info("Skipping actual order placement (ENABLE_ORDER_PLACEMENT is false.)")  # noqa

            # 6. Calculate Margin (Estimated)
            # Do this BEFORE fetching wallet so we have it even if wallet fetch fails
            try:
                notional_value = price * order_size * contract_value
                margin_used = notional_value / leverage
                logger.info(f"Estimated margin used: {margin_used} (Notional: {notional_value}, Leverage: {leverage})")
            except Exception as e:
                logger.error(f"Error calculating margin: {e}")
                margin_used = 0.0

            # 6. Fetch Wallet Balance (For Alert)
            remaining_margin = 0.0
            logger.info("Attempting to fetch wallet balance for notification...")
            try:
                wallet_data = client.get_wallet_balance()
                logger.info(f"Raw wallet data: {wallet_data}")
                
                collateral_currency = product.get('settling_asset', {}).get('symbol') or 'USD'
                logger.info(f"Looking for collateral currency: {collateral_currency}")

                balance_obj = {}
                
                # Robust parsing for different response structures
                if isinstance(wallet_data, list):
                    balance_obj = next((b for b in wallet_data if b.get('asset_symbol') == collateral_currency), {})
                elif isinstance(wallet_data, dict):
                    # Handle nested 'result' key which is common in Delta API
                    data_source = wallet_data.get('result', wallet_data)
                    
                    if isinstance(data_source, list):
                        balance_obj = next((b for b in data_source if b.get('asset_symbol') == collateral_currency), {})
                    elif isinstance(data_source, dict):
                        # Sometimes result might be the balance object itself or map of assets
                        if data_source.get('asset_symbol') == collateral_currency:
                            balance_obj = data_source
                        else:
                            # Try finding by key if it's a dict of usage
                            balance_obj = data_source.get(collateral_currency, {})

                if not balance_obj:
                    logger.warning(f"Could not find wallet balance for {collateral_currency} in response")
                    # Log available assets to help debug
                    if isinstance(wallet_data, dict):
                        data_source = wallet_data.get('result', wallet_data)
                        if isinstance(data_source, list):
                            available_assets = [b.get('asset_symbol', 'unknown') for b in data_source]
                            logger.warning(f"Available assets in response: {available_assets}")
                else:
                    logger.info(f"Found balance object: {balance_obj}")

                # Parse fields
                available_balance = float(balance_obj.get('available_balance', 0.0))
                remaining_margin = available_balance
                logger.info(f"Fetched wallet balance for {collateral_currency}: {remaining_margin}")

            except Exception as e:
                logger.error(f"Failed to fetch wallet details: {e}", exc_info=True)
        
        # 7. Extract PnL and Fees (for exit signals)
        pnl = None
        funding_charges = None
        trading_fees = None
        funding_txns: list = []     # raw txns kept for fee breakdown message
        trading_fee_txns: list = []

        if not is_entry and active_position:
            try:
                # Extract unrealized PnL (will be realized after exit)
                pnl = float(active_position.get('unrealized_pnl', 0.0))

                # Compute trade time range (reused for both funding and fee fetches)
                entry_ts_us = _parse_position_timestamp_us(active_position.get("created_at"))
                exit_ts_us = int(time.time() * 1_000_000)

                # Fetch actual funding debits/credits from wallet transactions
                # for the duration of this trade (entry time → now)
                if entry_ts_us and mode != "paper":
                    try:
                        txns = client.get_funding_transactions(entry_ts_us, exit_ts_us, product_id=product_id)
                        if txns:
                            funding_txns = txns
                            funding_charges = sum(float(t.get("amount", 0)) for t in txns)
                            logger.info(
                                f"Funding from wallet txns: ${funding_charges:+,.4f}"
                                f" ({len(txns)} transactions) for product_id: {product_id}"
                            )
                        else:
                            funding_charges = float(active_position.get('funding_pnl', 0.0))
                    except Exception as fe:
                        logger.warning(f"Funding transaction fetch failed, using position field: {fe}")
                        funding_charges = float(active_position.get('funding_pnl', 0.0))
                else:
                    funding_charges = float(active_position.get('funding_pnl', 0.0))

                # Fetch actual trading fees (entry + all partials + final exit) from wallet
                if entry_ts_us and mode != "paper":
                    try:
                        fee_txns = client.get_trading_fee_transactions(entry_ts_us, exit_ts_us, product_id=product_id)
                        if fee_txns:
                            trading_fee_txns = fee_txns
                            # Fee amounts are negative debits; use abs() for display
                            trading_fees = sum(abs(float(t.get("amount", 0))) for t in fee_txns)
                            logger.info(
                                f"Trading fees from wallet txns: ${trading_fees:,.4f}"
                                f" ({len(fee_txns)} transactions) for product_id: {product_id}"
                            )
                        else:
                            trading_fees = float(active_position.get('commission', 0.0))
                    except Exception as fe:
                        logger.warning(f"Trading fee transaction fetch failed, using position field: {fe}")
                        trading_fees = float(active_position.get('commission', 0.0))
                else:
                    trading_fees = float(active_position.get('commission', 0.0))

                logger.info(f"Exit metrics - PnL: ${pnl:+,.2f}, Fees: ${trading_fees:,.4f}, Funding: ${funding_charges:+,.4f}")
            except Exception as e:
                logger.warning(f"Failed to extract PnL/fees from position: {e}")
        
        # 8. Send Alert
        try:
            notifier.send_trade_alert(
                symbol=symbol,
                side=action, # "ENTRY_LONG" etc.
                price=execution_price if execution_price and mode != "paper" else price,
                rsi=rsi,
                reason=reason + (" [PAPER]" if mode == "paper" else ""),
                margin_used=margin_used if is_entry else None,
                remaining_margin=remaining_margin,
                strategy_name=strategy_name,
                pnl=pnl,
                funding_charges=funding_charges,
                trading_fees=trading_fees,
                market_price=market_price,
                lot_size=lot_size,
                # Pass configured target margin so Discord/email shows the capital allocation setting
                target_margin=target_margin if is_entry else None,
                timeframe=timeframe
            )
        except Exception as e:
            logger.error(f"Failed to send trade alert: {e}")

        # 8b. Send fee breakdown as a separate Discord message (exit signals, live mode only)
        if not is_entry and mode != "paper" and (funding_txns or trading_fee_txns):
            try:
                notifier.send_fee_breakdown(symbol, funding_txns, trading_fee_txns)
            except Exception as e:
                logger.warning(f"Failed to send fee breakdown: {e}")

        # 9. Journal Trade to Firestore
        # This happens after successful execution and notification
        # Determine entry_price and exit_price based on trade type
        entry_price_for_journal = None
        exit_price_for_journal = None
        
        # Get execution price (actual fill price from exchange)
        actual_execution_price = None
        if order and not mode == "paper":
            actual_execution_price = float(order.get('avg_fill_price', 0)) if order.get('avg_fill_price') else None
        
        # Generate or retrieve trade_id to link entry and exit
        trade_id = None
        
        if is_entry:
            # For entries, the execution price becomes the entry price
            entry_price_for_journal = actual_execution_price or price
            # Generate a unique trade_id for this new trade
            timestamp_str = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            trade_id = f"{symbol}_{strategy_name or 'unknown'}_{timestamp_str}_{uuid.uuid4().hex[:8]}"
            logger.info(f"Generated trade_id for entry: {trade_id}")
        else:
            # For exits, the execution price becomes the exit price
            exit_price_for_journal = actual_execution_price or price
            # Try to get entry price from active_position if available
            if active_position:
                entry_price_for_journal = float(active_position.get('entry_price', 0.0)) or None
            
            # Try to get trade_id from order metadata or generate a fallback
            # Note: Ideally this should be stored with the position in strategy state
            # For now, we'll create a consistent ID based on symbol and entry price
            if active_position and active_position.get('entry_price'):
                # Create a consistent trade_id based on entry details
                # This is a fallback; ideally strategies should store trade_id
                entry_ts = active_position.get('created_at', '')  # If available
                trade_id = f"{symbol}_{strategy_name or 'unknown'}_{entry_ts}" if entry_ts else None
        
        try:
            journal_trade(
                symbol=symbol,
                action=action,
                side=side,
                price=price,  # Candle close price
                order_size=order_size,
                leverage=leverage,
                mode=mode,
                trade_id=trade_id,  # Links entry and exit together
                strategy_name=strategy_name,
                rsi=rsi,
                reason=reason,
                is_entry=is_entry,
                is_partial_exit=("PARTIAL" in action or action == "MILESTONE_EXIT"),
                entry_price=entry_price_for_journal,
                exit_price=exit_price_for_journal,
                execution_price=actual_execution_price or price,
                pnl=pnl,
                funding_charges=funding_charges,
                trading_fees=trading_fees,
                margin_used=margin_used,
                remaining_margin=remaining_margin,
                product_id=product_id,
                order_id=order.get('id') if order else None
            )
        except Exception as e:
            # Log error but don't fail the trade execution
            logger.error(f"Failed to journal trade to Firestore: {e}", exc_info=True)
        
        return {
            "success": True,
            "execution_price": execution_price
        }

    except Exception as e:
        logger.exception("Strategy Execution Failed", error=str(e))
        notifier.send_error("Execution Failed", str(e))
        return {"success": False, "error": str(e)}
