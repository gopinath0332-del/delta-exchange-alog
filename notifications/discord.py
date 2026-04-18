"""Discord notification handler."""

import time
import requests
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.logger import get_logger

logger = get_logger(__name__)


class DiscordNotifier:
    """Handles sending notifications to Discord via Webhooks."""

    def __init__(self, webhook_url: str):
        """
        Initialize Discord notifier.

        Args:
            webhook_url: Discord Webhook URL
        """
        self.webhook_url = webhook_url
        self.last_alert_time: Dict[str, float] = {}
        self.throttle_interval = 60  # Min seconds between identical alerts
        
    def _f(self, val: Optional[float], decimals: int = 8) -> str:
        """Format currency to full precision, removing trailing zeros."""
        if val is None:
            return "0"
        return f"{val:,.{decimals}f}".rstrip('0').rstrip('.')

    def send_message(self, message: str, title: Optional[str] = None, color: Optional[int] = None):
        """
        Send a simple message to Discord.

        Args:
            message: Message content
            title: Optional title for embed
            color: Optional color code (integer)
        """
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured")
            return

        try:
            payload = {}
            
            if title:
                # Use embed for cleaner look
                embed = {
                    "title": title,
                    "description": message,
                    "color": color or 3447003,  # Default Blue
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }
                payload["embeds"] = [embed]
            else:
                payload["content"] = message

            response = requests.post(self.webhook_url, json=payload, timeout=5)
            response.raise_for_status()
            logger.debug("Discord notification sent")

        except requests.RequestException as e:
            logger.error("Discord connection failed", error=str(e))
        except Exception as e:
            logger.error("Failed to send Discord notification", error=str(e))

    def send_trade_alert(self, 
                        symbol: str, 
                        side: str, 
                        price: float, 
                        rsi: float, 
                        reason: str,
                        margin_used: Optional[float] = None,
                        remaining_margin: Optional[float] = None,
                        strategy_name: Optional[str] = None,
                        pnl: Optional[float] = None,
                        funding_charges: Optional[float] = None,
                        trading_fees: Optional[float] = None,
                        market_price: Optional[float] = None,
                        lot_size: Optional[int] = None,
                        target_margin: Optional[float] = None,
                        timeframe: Optional[str] = None,
                        stop_loss_price: Optional[float] = None,
                        atr: Optional[float] = None,
                        justification: Optional[str] = None,
                        mode: str = "live"):
        """
        Send a formatted trade alert with ANSI color codes.

        Args:
            symbol: Trading symbol (e.g. BTCUSD)
            side: Trade side (LONG/SHORT)
            price: Entry price
            rsi: RSI value
            reason: Trigger reason
            margin_used: Margin used directly for this trade (actual calculated margin)
            remaining_margin: Remaining wallet balance
            strategy_name: Name of the strategy executing the trade
            pnl: Realized profit/loss (for exit signals)
            funding_charges: Total funding fees paid/received
            trading_fees: Commission/trading fees
            market_price: Actual market price (LTP) if different from order/signal price
            lot_size: Number of contracts/lots in the order
            target_margin: Configured target margin from .env (e.g. TARGET_MARGIN_PAXG=30)
            mode: Trading mode (live or paper)
        """
        # Add timeframe to title if available
        title_suffix = f" ({timeframe})" if timeframe else ""
        title = f"🚀 TRADING SIGNAL: {side} {symbol}{title_suffix}"
        color = 5763719 if "LONG" in side.upper() else 15548997  # Green for Long, Red for Short
        
        # ANSI Color Codes
        # \u001b[1;37m = Bold White
        # \u001b[0;36m = Cyan
        # \u001b[0;33m = Yellow
        # \u001b[0;35m = Magenta
        # \u001b[0;31m = Red
        # \u001b[0m = Reset
        
        message = ""
        if strategy_name:
            message += f"Strategy: \u001b[1;37m{strategy_name}\u001b[0m\n"
        
        # Trading Mode
        mode_color = "1;32" if mode.lower() == "live" else "1;36"
        message += f"Trading Mode: \u001b[{mode_color}m{mode.upper()}\u001b[0m\n"

        if timeframe:
            message += f"Timeframe: \u001b[1;37m{timeframe}\u001b[0m\n"
            
        # Volatility Rating (for entries)
        if target_margin and margin_used and "ENTRY" in side.upper():
            # % reduction from target margin
            reduction_pct = ((target_margin - margin_used) / target_margin) * 100
            
            if reduction_pct <= 1:
                rating = "Stable"
                adj_text = "Full size"
            elif reduction_pct < 20:
                rating = "Moderate"
                adj_text = f"-{reduction_pct:.1f}% adjustment"
            elif reduction_pct < 50:
                rating = "High"
                adj_text = f"-{reduction_pct:.1f}% adjustment"
            else:
                rating = "Extreme"
                adj_text = f"-{reduction_pct:.1f}% adjustment"
                
            message += f"Market Volatility: \u001b[1;37m{rating}\u001b[0m ({adj_text})\n"

        message += (
            f"Price: \u001b[0;36m${self._f(price)}\u001b[0m\n"
        )

        # Show Market Price if available and significantly different (> 0.05% diff)
        # OR if strictly requested to show context
        if market_price and market_price > 0:
            diff = abs(price - market_price)
            pct_diff = (diff / market_price) * 100
            
            # If price (HA) and market_price are different, show Market Price
            # We want to show it e.g. "Market Price: $22.28"
            if pct_diff > 0.01: # Show if diff > 0.01%
                message += f"Market Price: \u001b[0;36m${self._f(market_price)}\u001b[0m\n"

        message += (
            f"RSI: \u001b[0;33m{rsi:.2f}\u001b[0m\n"
        )
        
        # Show Stop Loss if available
        if stop_loss_price is not None:
            message += f"Stop Loss: \u001b[0;31m${self._f(stop_loss_price)}\u001b[0m\n"
        
        # Show lot size if available
        if lot_size is not None:
            message += f"Lot Size: \u001b[0;36m{lot_size}\u001b[0m contracts\n"
        
        # Show target margin (configured capital allocation) for entry signals
        # This tells the trader what margin budget was set for this position
        if target_margin is not None:
            message += f"Target Margin: \u001b[0;35m${self._f(target_margin)}\u001b[0m\n"
        
        # Color-code [DISABLED] tag in reason if present
        if "[DISABLED]" in reason:
            reason = reason.replace("[DISABLED]", "\u001b[0;31m[DISABLED]\u001b[0m")
        
        message += f"Reason: {reason}\n"
        message += f"Time: {time.strftime('%H:%M:%S UTC')}"
        
        if margin_used is not None:
            message += f"\nMargin Used: \u001b[0;35m${self._f(margin_used)}\u001b[0m"
        
        # Show PnL, funding, and fees only for exit signals
        if "EXIT" in side.upper():
            if pnl is not None:
                # Color code: green for profit, red for loss
                pnl_color = "0;32" if pnl >= 0 else "0;31"
                message += f"\nP&L: \u001b[{pnl_color}m${self._f(pnl)}\u001b[0m"
            
            if funding_charges is not None:
                message += f"\nFunding: ${self._f(funding_charges)}"
            
            if trading_fees is not None:
                message += f"\nFees: ${self._f(trading_fees)}"
            
        if remaining_margin is not None:
            message += f"\nRemaining Wallet: \u001b[0;36m${self._f(remaining_margin)}\u001b[0m"
        
        # Sizing Justification (New Field)
        if justification:
            message += f"\n\n\u001b[1;37mSizing Justification:\u001b[0m\n{justification}"
        
        # Wrap in ANSI code block for Discord
        formatted_message = f"```ansi\n{message}\n```"
        
        # Send as embed with color
        try:
            embed = {
                "title": title,
                "description": formatted_message,
                "color": color,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            
            payload = {"embeds": [embed]}
            
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            response.raise_for_status()
            logger.debug("Discord trade alert sent with colors")

        except requests.RequestException as e:
            logger.error("Discord connection failed", error=str(e))
        except Exception as e:
            logger.error("Failed to send Discord notification", error=str(e))

    def _format_ts(self, created_at: Any) -> str:
        """Parse a transaction timestamp (µs int or ISO string) to 'YYYY-MM-DD HH:MM UTC'."""
        try:
            if isinstance(created_at, (int, float)):
                ts = float(created_at)
                if ts > 1e15:        # microseconds
                    ts /= 1_000_000
                elif ts > 1e12:      # milliseconds
                    ts /= 1_000
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            return "unknown"

    def send_fee_breakdown(
        self,
        symbol: str,
        funding_txns: List[Dict[str, Any]],
        trading_fee_txns: List[Dict[str, Any]],
    ) -> None:
        """
        Send a combined fee breakdown message listing all per-transaction details.

        Args:
            symbol: Trading symbol (e.g. BTCUSD)
            funding_txns: List of funding wallet transaction dicts
            trading_fee_txns: List of trading fee wallet transaction dicts
        """
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured")
            return

        if not funding_txns and not trading_fee_txns:
            return

        lines = []

        if funding_txns:
            lines.append("\u001b[1;37mFUNDING\u001b[0m")
            funding_total = 0.0
            for t in funding_txns:
                ts = self._format_ts(t.get("created_at"))
                amt = float(t.get("amount", 0))
                funding_total += amt
                color = "0;32" if amt >= 0 else "0;31"
                lines.append(f"  {ts}  \u001b[{color}m${self._f(amt)}\u001b[0m")
            subtotal_color = "0;32" if funding_total >= 0 else "0;31"
            lines.append(f"Subtotal: \u001b[{subtotal_color}m${self._f(funding_total)}\u001b[0m")

        if funding_txns and trading_fee_txns:
            lines.append("")

        if trading_fee_txns:
            lines.append("\u001b[1;37mTRADING FEES\u001b[0m")
            fee_total = 0.0
            for t in trading_fee_txns:
                ts = self._format_ts(t.get("created_at"))
                amt = float(t.get("amount", 0))
                fee_total += amt
                lines.append(f"  {ts}  \u001b[0;31m${self._f(abs(amt))}\u001b[0m")
            lines.append(f"Subtotal: \u001b[0;31m${self._f(abs(fee_total))}\u001b[0m")

        # Net fees line
        if funding_txns and trading_fee_txns:
            lines.append("")
            funding_sum = sum(float(t.get("amount", 0)) for t in funding_txns)
            fee_sum = sum(float(t.get("amount", 0)) for t in trading_fee_txns)
            net = funding_sum + fee_sum
            net_color = "0;32" if net >= 0 else "0;31"
            lines.append(f"Net Fees: \u001b[{net_color}m${self._f(net)}\u001b[0m")

        body = "\n".join(lines)
        formatted = f"```ansi\n{body}\n```"

        try:
            embed = {
                "title": f"📋 Fee Breakdown — {symbol}",
                "description": formatted,
                "color": 3447003,  # Neutral blue
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            response = requests.post(self.webhook_url, json={"embeds": [embed]}, timeout=5)
            response.raise_for_status()
            logger.debug("Discord fee breakdown sent", symbol=symbol)
        except requests.RequestException as e:
            logger.error("Discord connection failed", error=str(e))
        except Exception as e:
            logger.error("Failed to send fee breakdown", error=str(e))

    def send_status_message_with_color(self, title: str, message: str, order_placement_enabled: Optional[bool] = None):
        """
        Send a status message with ANSI color codes for better formatting.
        
        Args:
            title: Message title
            message: Message content (can include ANSI color codes)
            order_placement_enabled: If provided, will color-code the order placement status
        """
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured")
            return

        try:
            # Determine embed color based on order placement status
            if order_placement_enabled is not None:
                embed_color = 5763719 if order_placement_enabled else 15548997  # Green if enabled, Red if disabled
            else:
                embed_color = 3447003  # Default Blue
            
            # Format message with ANSI color codes
            # Discord supports ANSI in code blocks with ```ansi
            formatted_message = f"```ansi\n{message}\n```"
            
            embed = {
                "title": title,
                "description": formatted_message,
                "color": embed_color,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            
            payload = {"embeds": [embed]}
            
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            response.raise_for_status()
            logger.debug("Discord status message sent with color")

        except requests.RequestException as e:
            logger.error("Discord connection failed", error=str(e))
        except Exception as e:
            logger.error("Failed to send Discord notification", error=str(e))
