"""
Centralized trading execution logic.
Handles order placement, leverage setting, and margin calculations.
"""

from typing import Optional
from core.logger import get_logger
from api.rest_client import DeltaRestClient
from notifications.manager import NotificationManager

logger = get_logger(__name__)

def execute_strategy_signal(
    client: DeltaRestClient,
    notifier: NotificationManager,
    symbol: str,
    action: str,
    price: float,
    rsi: float,
    reason: str,
    mode: str = "live"
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
        
        # 2. Determine Order Params
        order_size = 1 # Fixed 1 Lot
        leverage = 5   # Fixed 5x
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
        
        if not side:
            logger.warning(f"Unknown action: {action}")
            return

        # 3. Set Leverage (Only on Entry)
        if is_entry and mode != "paper":
            try:
                client.set_leverage(product_id, str(leverage))
                logger.info(f"Set leverage to {leverage}x for {symbol}")
            except Exception as e:
                logger.error(f"Failed to set leverage: {e}")
                # Continue anyway, might already be set
        
        # 4. Place Order (Market)
        if mode == "paper":
            logger.info(f"[PAPER] Simulating {side.upper()} order for {order_size} contract(s) of {symbol}")
            order = {"id": "PAPER_ORDER_ID"}
            margin_used = 0.0
            remaining_margin = 0.0
            # Estimate margin for dashboard consistency
            notional_value = price * order_size * contract_value
            margin_used = notional_value / leverage
        else:
            logger.info(f"Placing {side.upper()} order for {order_size} contract(s) of {symbol}")
            try:
                order = client.place_order(
                    product_id=product_id,
                    size=order_size,
                    side=side,
                    order_type="market_order"
                )
                logger.info(f"Order placed successfully: {order.get('id')}")
            except Exception as e:
                logger.error(f"Failed to place order: {e}")
                notifier.send_error(f"Order Failed: {symbol}", str(e))
                return

            # 5. Calculate Margin & Wallet (For Alert)
            margin_used = 0.0
            remaining_margin = 0.0
    
            try:
                # Fetch Wallet
                wallet_data = client.get_wallet_balance()
                
                collateral_currency = product.get('settling_asset', {}).get('symbol') or 'USDT'
                
                # Helper to find currency in wallet_data
                if isinstance(wallet_data, list):
                    balance_obj = next((b for b in wallet_data if b.get('asset_symbol') == collateral_currency), {})
                elif isinstance(wallet_data, dict) and 'result' in wallet_data:
                     # Check if result is list
                     res = wallet_data['result']
                     if isinstance(res, list):
                         balance_obj = next((b for b in res if b.get('asset_symbol') == collateral_currency), {})
                     else:
                         balance_obj = res # Maybe simple dict?
                else:
                    balance_obj = {}
    
                # Parse fields
                available_balance = float(balance_obj.get('available_balance', 0.0))
                remaining_margin = available_balance 
    
                # Calculate Estimated Margin for THIS order
                # Margin = (Price * Size * ContractValue) / Leverage
                notional_value = price * order_size * contract_value
                margin_used = notional_value / leverage
    
            except Exception as e:
                logger.warning(f"Failed to fetch margin details: {e}")
        
        # 6. Send Alert
        notifier.send_trade_alert(
            symbol=symbol,
            side=action, # "ENTRY_LONG" etc.
            price=price,
            rsi=rsi,
            reason=reason + (" [PAPER]" if mode == "paper" else ""),
            margin_used=margin_used if is_entry else None,
            remaining_margin=remaining_margin
        )

    except Exception as e:
        logger.exception("Strategy Execution Failed", error=str(e))
        notifier.send_error("Execution Failed", str(e))
