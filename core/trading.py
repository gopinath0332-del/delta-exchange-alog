"""
Centralized trading execution logic.
Handles order placement, leverage setting, and margin calculations.
"""

from typing import Optional
import os
from core.logger import get_logger
from api.rest_client import DeltaRestClient
from notifications.manager import NotificationManager

logger = get_logger(__name__)

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
    order_size = 1
    leverage = 5
    
    # 3. Load overrides
    try:
        order_size = int(os.getenv(f"ORDER_SIZE_{base_asset}", str(order_size)))
        leverage = int(os.getenv(f"LEVERAGE_{base_asset}", str(leverage)))
    except ValueError:
        logger.warning(f"Invalid integer configuration for {base_asset}, using defaults.")

    # 4. Check Enable Flag
    env_var_key = f"ENABLE_ORDER_PLACEMENT_{base_asset}"
    enable_orders = os.getenv(env_var_key, "false").lower() == "true"
    
    return {
        "order_size": order_size,
        "leverage": leverage,
        "enabled": enable_orders,
        "base_asset": base_asset
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
    strategy_name: Optional[str] = None
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
        order_size = config['order_size']
        leverage = config['leverage']
        enable_orders = config['enabled']
        base_asset = config['base_asset']
        
        side = None
        is_entry = False
        
        if action == "ENTRY_LONG":
            side = "buy"
            is_entry = True
        elif action == "ENTRY_SHORT":
            side = "sell"
            is_entry = True
        elif action == "EXIT_LONG":
            side = "sell" # Close Long = Sell
        elif action == "EXIT_SHORT":
            side = "buy" # Close Short = Buy
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
        if mode == "paper":
            logger.info(f"[PAPER] Simulating {side.upper()} order for {order_size} contract(s) of {symbol}")
            order = {"id": "PAPER_ORDER_ID"}
            margin_used = 0.0
            remaining_margin = 0.0
            # Estimate margin for dashboard consistency
            notional_value = price * order_size * contract_value
            margin_used = notional_value / leverage
        else:
            # 7. Execute Order if Enabled
            execution_price = None
            
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
                    
                    # Attempt to get fill price from response
                    if order.get('avg_fill_price'):
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
            else:
                 logger.info("Skipping actual order placement (ENABLE_ORDER_PLACEMENT is false).")

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
            try:
                wallet_data = client.get_wallet_balance()
                logger.debug(f"Raw wallet data: {wallet_data}")
                
                collateral_currency = product.get('settling_asset', {}).get('symbol') or 'USDT'
                logger.debug(f"Looking for collateral currency: {collateral_currency}")

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

                # Parse fields
                available_balance = float(balance_obj.get('available_balance', 0.0))
                remaining_margin = available_balance
                logger.info(f"Fetched wallet balance for {collateral_currency}: {remaining_margin}")

            except Exception as e:
                logger.warning(f"Failed to fetch wallet details: {e}")
        
        # 6. Send Alert
        try:
            notifier.send_trade_alert(
                symbol=symbol,
                side=action, # "ENTRY_LONG" etc.
                price=price if mode == "paper" else (float(order.get('avg_fill_price', price)) if order else price),
                rsi=rsi,
                reason=reason + (" [PAPER]" if mode == "paper" else ""),
                margin_used=margin_used if is_entry else None,
                remaining_margin=remaining_margin,
                strategy_name=strategy_name
            )
        except Exception as e:
            logger.error(f"Failed to send trade alert: {e}")
        
        return {
            "success": True,
            "execution_price": execution_price
        }

    except Exception as e:
        logger.exception("Strategy Execution Failed", error=str(e))
        notifier.send_error("Execution Failed", str(e))
        return {"success": False, "error": str(e)}
