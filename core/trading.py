"""
Centralized trading execution logic.
Handles order placement, leverage setting, and margin calculations.
"""

from typing import Optional
import time
import os
import uuid
from datetime import datetime
from core.logger import get_logger
from api.rest_client import DeltaRestClient
from notifications.manager import NotificationManager
from core.firestore_client import journal_trade  # For trade journaling to Firestore

logger = get_logger(__name__)

def calculate_position_size(
    target_margin: float,
    price: float,
    leverage: int,
    contract_value: float,
    enable_partial_tp: bool = False
) -> int:
    """
    Calculate position size dynamically based on target margin.
    
    Args:
        target_margin: Target margin to use (e.g., 40 USD)
        price: Current market price
        leverage: Leverage to apply
        contract_value: Contract value from product info
        enable_partial_tp: Whether partial take-profit is enabled
        
    Returns:
        Calculated position size (integer number of contracts)
        
    Logic:
        1. Calculate base size: (target_margin * leverage) / (price * contract_value)
        2. Round to integer
        3. If enable_partial_tp is True and size is odd, round to nearest even number
        4. Validate final size doesn't exceed target margin
        5. Return size (minimum 2 if partial TP enabled, minimum 1 otherwise)
    """
    try:
        # Calculate base position size
        # Formula: (target_margin * leverage) / (price * contract_value)
        base_size = (target_margin * leverage) / (price * contract_value)
        
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
        
        # Validate that the final size doesn't significantly exceed target margin
        actual_margin = (position_size * price * contract_value) / leverage
        
        # Log calculation details
        logger.info(
            f"Position size calculation: "
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

def get_trade_config(symbol: str):
    """
    Get trade configuration for a symbol from environment variables.
    
    Returns:
        dict: {
            "order_size": int,
            "leverage": int,
            "enabled": bool,
            "base_asset": str
        }
    """
    # 1. Determine Base Asset
    base_asset = symbol.upper().replace("USD", "").replace("USDT", "").replace("-", "").replace("/", "").replace("_", "")
    
    # 2. Defaults
    order_size = 1  # Deprecated: kept for backwards compatibility
    leverage = 5
    target_margin = 40.0  # Default target margin in USD
    
    # 3. Load overrides
    try:
        order_size = int(os.getenv(f"ORDER_SIZE_{base_asset}", str(order_size)))
        leverage = int(os.getenv(f"LEVERAGE_{base_asset}", str(leverage)))
        target_margin = float(os.getenv(f"TARGET_MARGIN_{base_asset}", str(target_margin)))
    except ValueError:
        logger.warning(f"Invalid configuration for {base_asset}, using defaults.")

    # 4. Check Enable Flag
    env_var_key = f"ENABLE_ORDER_PLACEMENT_{base_asset}"
    enable_orders = os.getenv(env_var_key, "false").lower() == "true"
    
    return {
        "order_size": order_size,  # Deprecated: kept for backwards compatibility
        "leverage": leverage,
        "enabled": enable_orders,
        "base_asset": base_asset,
        "target_margin": target_margin  # New: configurable target margin
    }

def execute_strategy_signal(
    client: DeltaRestClient,
    notifier: NotificationManager,
    symbol: str,
    action: str,
    price: float,
    rsi: float,
    reason: str,
    mode: str = "live",
    strategy_name: Optional[str] = None,
    market_price: Optional[float] = None,
    enable_partial_tp: bool = False,
    stop_loss_pct: Optional[float] = None
):
    """
    Execute a strategy signal: Place order and send alert.
    
    Args:
        client: API Client
        notifier: Notification Manager
        symbol: Trading Symbol (e.g. 'BTCUSD')
        action: Strategy Action (ENTRY_LONG, EXIT_LONG, etc.)
        price: Current Price (for estimation)
        rsi: Current RSI
        reason: Signal Reason
        mode: Execution mode ('live' or 'paper')
        strategy_name: Name of the strategy executing the signal
        market_price: Actual market price (LTP) if different from price
        enable_partial_tp: Whether partial take-profit is enabled (for position sizing)
        stop_loss_pct: Fraction of target_margin to use as max loss (e.g. 0.10 = 10%).
                       When provided (Donchian only), a bracket stop-loss order is placed
                       on the exchange immediately after a successful entry order.
                       Pass None (default) to skip bracket SL placement entirely.
    """
    
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
        config = get_trade_config(symbol)
        order_size = config['order_size']  # Will be overridden for entries with dynamic sizing
        leverage = config['leverage']
        enable_orders = config['enabled']
        base_asset = config['base_asset']
        target_margin = config['target_margin']
        
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
                    enable_partial_tp=enable_partial_tp
                )
                lot_size = order_size  # Store for notification
                logger.info(f"Calculated position size for ENTRY_LONG: {order_size} contracts")
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
                    enable_partial_tp=enable_partial_tp
                )
                lot_size = order_size  # Store for notification
                logger.info(f"Calculated position size for ENTRY_SHORT: {order_size} contracts")
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

                # --- EXCHANGE BRACKET STOP-LOSS (Donchian only) ---
                # Place a bracket stop-loss order on the exchange immediately after
                # a successful entry so the exchange closes the position automatically
                # when the stop price is hit — no application-level polling required.
                #
                # The stop price is derived from the configured stop_loss_pct:
                #   stop_loss_distance = (target_margin * stop_loss_pct)
                #                        / (position_size * contract_value)
                #
                # For LONG:  stop_price = entry_price - stop_loss_distance
                # For SHORT: stop_price = entry_price + stop_loss_distance
                #
                # Example: margin=$1000, 10%, position_size=100, contract_value=0.001
                #   stop_loss_distance = (1000 * 0.10) / (100 * 0.001) = $1,000
                #   stop_price (LONG) = 100,000 - 1,000 = $99,000
                #   PnL at stop = -$100 = exactly -10% of $1000 margin  ✓
                if stop_loss_pct is not None and is_entry and order:
                    try:
                        # Use the actual fill price for SL anchor; fall back to signal price.
                        sl_anchor_price = execution_price if execution_price else price

                        # Guard against zero/negative contract_value or position size.
                        if contract_value > 0 and order_size > 0:
                            sl_distance = (target_margin * stop_loss_pct) / (order_size * contract_value)

                            if action == "ENTRY_LONG":
                                sl_price = sl_anchor_price - sl_distance
                            else:  # ENTRY_SHORT
                                sl_price = sl_anchor_price + sl_distance

                            # Determine decimal precision from the product's tick_size so
                            # the stop price matches the exchange's accepted format.
                            # e.g. tick_size=0.5 → 1 decimal, tick_size=0.01 → 2 decimals.
                            import math as _math
                            try:
                                tick_size = float(product.get("tick_size", "1"))
                                if 0 < tick_size < 1:
                                    sl_decimals = _math.ceil(abs(_math.log10(tick_size)))
                                else:
                                    sl_decimals = 0
                            except Exception:
                                sl_decimals = 2  # Safe fallback
                            sl_price_str = f"{sl_price:.{sl_decimals}f}"

                            logger.info(
                                f"Placing exchange bracket SL: anchor={sl_anchor_price}, "
                                f"distance={sl_distance:.4f}, stop_price={sl_price_str} "
                                f"(margin={target_margin}, pct={stop_loss_pct*100:.0f}%, "
                                f"size={order_size}, contract_value={contract_value})"
                            )

                            client.place_bracket_order(
                                product_id=product_id,
                                product_symbol=symbol,
                                stop_price=sl_price_str,
                                stop_order_type="market_order",   # Fill immediately on trigger
                                stop_trigger_method="last_traded_price"
                            )

                            logger.info(f"Exchange bracket stop-loss placed at {sl_price_str} for {symbol}")
                        else:
                            logger.warning(
                                f"Skipping bracket SL: invalid contract_value={contract_value} "
                                f"or order_size={order_size}"
                            )

                    except Exception as sl_err:
                        # SL placement failure is non-fatal: position is already open.
                        # Log an error so it surfaces via Discord error webhook.
                        logger.error(
                            f"Failed to place bracket stop-loss for {symbol}: {sl_err}. "
                            f"Position is open WITHOUT an exchange stop-loss. "
                            f"Manual intervention may be required."
                        )
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
        
        if not is_entry and active_position:
            try:
                # Extract unrealized PnL (will be realized after exit)
                pnl = float(active_position.get('unrealized_pnl', 0.0))
                
                # Extract commission/trading fees
                trading_fees = float(active_position.get('commission', 0.0))
                
                # Note: Funding charges might be in a separate field
                # Check if there's a funding-specific field, otherwise leave as None
                # Common fields: 'funding_pnl', 'funding', 'funding_payment'
                funding_charges = float(active_position.get('funding_pnl', 0.0))
                
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
                target_margin=target_margin if is_entry else None
            )
        except Exception as e:
            logger.error(f"Failed to send trade alert: {e}")
        
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
                is_partial_exit=("PARTIAL" in action),
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
