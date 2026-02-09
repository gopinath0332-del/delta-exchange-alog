"""
EMA Cross Strategy for Bitcoin (BTCUSD)

Strategy Logic (from btc-ema-cross.pine):
- Fast EMA (default: 10) and Slow EMA (default: 20)
- Long Entry: Fast EMA crosses above Slow EMA
- Short Entry: Fast EMA crosses below Slow EMA
- Long Exit: Opposite cross (Fast crosses below Slow)
- Short Exit: Opposite cross (Fast crosses above Slow)
- Supports LONG only, SHORT only, or BOTH directions
- Allow Flip: When enabled, can close and reverse on the same bar
"""

import logging
from typing import Dict, Optional, Tuple, Any
import pandas as pd
import numpy as np
from core.config import get_config
from core.candle_utils import get_closed_candle_index

logger = logging.getLogger(__name__)


class EMACrossStrategy:
    """
    EMA Crossover Strategy for BTCUSD (10/20 EMA)
    
    This strategy generates signals based on EMA crossovers:
    - Bullish Cross (10 EMA > 20 EMA): Long Entry / Short Exit
    - Bearish Cross (10 EMA < 20 EMA): Short Entry / Long Exit
    """
    
    def __init__(self):
        # Load Configuration from settings.yaml
        config = get_config()
        cfg = config.settings.get("strategies", {}).get("ema_cross", {})
        
        # Strategy Parameters
        self.trade_mode = cfg.get("trade_mode", "Both")  # "Long", "Short", "Both"
        self.fast_ema_length = cfg.get("fast_ema_length", 10)
        self.slow_ema_length = cfg.get("slow_ema_length", 20)
        self.allow_flip = cfg.get("allow_flip", True)  # Allow same-bar close & reverse
        
        # Mode Flags
        self.allow_long = self.trade_mode in ["Long", "Both"]
        self.allow_short = self.trade_mode in ["Short", "Both"]
        
        # Dashboard Label
        self.indicator_label = "EMA"
        self.timeframe = "4h"  # Default, can be overridden
        
        # Position State
        self.current_position = 0  # 1 for Long, -1 for Short, 0 for Flat
        self.last_entry_price = 0.0
        self.entry_price = None
        
        # Indicator Cache (for dashboard display)
        self.last_fast_ema = 0.0
        self.last_slow_ema = 0.0
        
        # Closed Candle Cache
        self.last_closed_time_str = "-"
        self.last_closed_fast_ema = 0.0
        self.last_closed_slow_ema = 0.0
        
        # Trade History
        self.trades = []
        self.active_trade = None
        
        logger.info(f"EMACrossStrategy initialized: Mode={self.trade_mode}, "
                   f"Fast EMA={self.fast_ema_length}, Slow EMA={self.slow_ema_length}, "
                   f"Allow Flip={self.allow_flip}")
    
    def calculate_indicators(self, df: pd.DataFrame, current_time: Optional[float] = None) -> Tuple[float, float]:
        """
        Calculate Fast and Slow EMA values.
        
        Args:
            df: DataFrame with OHLC data
            current_time: Current timestamp in seconds
            
        Returns:
            Tuple of (fast_ema, slow_ema)
        """
        try:
            min_periods = max(self.fast_ema_length, self.slow_ema_length) + 1
            if len(df) < min_periods:
                return 0.0, 0.0
            
            if current_time is None:
                import time
                current_time = time.time()
            
            # Calculate EMAs
            close = df['close'].astype(float)
            fast_ema_series = close.ewm(span=self.fast_ema_length, adjust=False).mean()
            slow_ema_series = close.ewm(span=self.slow_ema_length, adjust=False).mean()
            
            current_fast_ema = fast_ema_series.iloc[-1]
            current_slow_ema = slow_ema_series.iloc[-1]
            
            # Cache for dashboard
            self.last_fast_ema = current_fast_ema
            self.last_slow_ema = current_slow_ema
            
            # Determine closed candle index based on timeframe
            # For 4H candle: 4 * 60 * 60 = 14400 seconds
            candle_seconds = 14400  # 4 hours
            last_candle_ts = df['time'].iloc[-1]
            if last_candle_ts > 1e11:
                last_candle_ts /= 1000  # Convert ms to seconds
            
            diff = current_time - last_candle_ts
            closed_idx = -1 if diff >= candle_seconds else -2
            
            # Cache closed candle values
            if len(df) >= abs(closed_idx):
                import datetime
                ts = df['time'].iloc[closed_idx]
                if ts > 1e11:
                    ts /= 1000
                self.last_closed_time_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M')
                self.last_closed_fast_ema = fast_ema_series.iloc[closed_idx]
                self.last_closed_slow_ema = slow_ema_series.iloc[closed_idx]
            else:
                self.last_closed_time_str = "-"
                self.last_closed_fast_ema = 0.0
                self.last_closed_slow_ema = 0.0
            
            return current_fast_ema, current_slow_ema
            
        except Exception as e:
            logger.error(f"Error calculating EMA indicators: {e}")
            return 0.0, 0.0
    
    def check_signals(self, df: pd.DataFrame, current_time_ms: float) -> Tuple[Optional[str], str]:
        """
        Check for EMA crossover signals using closed candle logic.
        
        Args:
            df: DataFrame with OHLC data
            current_time_ms: Current timestamp in milliseconds
            
        Returns:
            Tuple of (action, reason) where action is ENTRY_LONG, EXIT_LONG, 
            ENTRY_SHORT, EXIT_SHORT, or None
        """
        min_periods = max(self.fast_ema_length, self.slow_ema_length) + 2
        if df.empty or len(df) < min_periods:
            return None, ""
        
        current_time_s = current_time_ms / 1000.0
        fast_ema, slow_ema = self.calculate_indicators(df, current_time=current_time_s)
        
        # Determine Closed Candle Index (for 4H timeframe)
        candle_seconds = 14400  # 4 hours
        last_candle_ts = df['time'].iloc[-1]
        if last_candle_ts > 1e11:
            last_candle_ts /= 1000
        
        diff = current_time_s - last_candle_ts
        closed_idx = -1 if diff >= candle_seconds else -2
        prev_idx = closed_idx - 1
        
        # Calculate EMAs at closed and previous indices
        close = df['close'].astype(float)
        fast_ema_series = close.ewm(span=self.fast_ema_length, adjust=False).mean()
        slow_ema_series = close.ewm(span=self.slow_ema_length, adjust=False).mean()
        
        fast_closed = fast_ema_series.iloc[closed_idx]
        slow_closed = slow_ema_series.iloc[closed_idx]
        fast_prev = fast_ema_series.iloc[prev_idx]
        slow_prev = slow_ema_series.iloc[prev_idx]
        
        # Detect Crossovers
        # Bullish Cross: Fast was below Slow, now Fast is above Slow
        bullish_cross = (fast_prev <= slow_prev) and (fast_closed > slow_closed)
        
        # Bearish Cross: Fast was above Slow, now Fast is below Slow
        bearish_cross = (fast_prev >= slow_prev) and (fast_closed < slow_closed)
        
        action = None
        reason = ""
        
        # --- SIGNAL LOGIC ---
        
        # LONG SIGNALS
        if self.allow_long and bullish_cross:
            if self.current_position == 0:
                # Flat -> Long Entry
                action = "ENTRY_LONG"
                reason = f"Bullish Cross: Fast EMA ({fast_closed:.2f}) crossed above Slow EMA ({slow_closed:.2f})"
                self.entry_price = df['close'].iloc[closed_idx]
                return action, reason
            
            elif self.current_position == -1:
                # Short -> Exit Short (and optionally flip to Long)
                if self.allow_flip:
                    # Will handle flip in execution - first exit
                    action = "EXIT_SHORT"
                    reason = f"Bullish Cross: Fast EMA ({fast_closed:.2f}) crossed above Slow EMA ({slow_closed:.2f})"
                    return action, reason
                else:
                    action = "EXIT_SHORT"
                    reason = f"Bullish Cross: Fast EMA ({fast_closed:.2f}) crossed above Slow EMA ({slow_closed:.2f})"
                    return action, reason
        
        # SHORT SIGNALS
        if self.allow_short and bearish_cross:
            if self.current_position == 0:
                # Flat -> Short Entry
                action = "ENTRY_SHORT"
                reason = f"Bearish Cross: Fast EMA ({fast_closed:.2f}) crossed below Slow EMA ({slow_closed:.2f})"
                self.entry_price = df['close'].iloc[closed_idx]
                return action, reason
            
            elif self.current_position == 1:
                # Long -> Exit Long (and optionally flip to Short)
                if self.allow_flip:
                    # Will handle flip in execution - first exit
                    action = "EXIT_LONG"
                    reason = f"Bearish Cross: Fast EMA ({fast_closed:.2f}) crossed below Slow EMA ({slow_closed:.2f})"
                    return action, reason
                else:
                    action = "EXIT_LONG"
                    reason = f"Bearish Cross: Fast EMA ({fast_closed:.2f}) crossed below Slow EMA ({slow_closed:.2f})"
                    return action, reason
        
        # EXIT SIGNALS (when not a crossover, but position needs to exit)
        if self.current_position == 1 and bearish_cross:
            action = "EXIT_LONG"
            reason = f"Bearish Cross Exit: Fast EMA ({fast_closed:.2f}) below Slow EMA ({slow_closed:.2f})"
            return action, reason
        
        if self.current_position == -1 and bullish_cross:
            action = "EXIT_SHORT"
            reason = f"Bullish Cross Exit: Fast EMA ({fast_closed:.2f}) above Slow EMA ({slow_closed:.2f})"
            return action, reason
        
        return None, ""
    
    def update_position_state(self, action: str, current_time_ms: float, 
                              indicators: Any = None, price: float = 0.0, reason: str = ""):
        """
        Update internal state after a trade action.
        
        Args:
            action: The trade action taken
            current_time_ms: Current timestamp in milliseconds
            indicators: Not used, kept for interface compatibility
            price: Execution price
            reason: Reason for the trade
        """
        import datetime
        
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms / 1000).strftime('%d-%m-%y %H:%M')
        
        if action == "ENTRY_LONG":
            self.current_position = 1
            self.last_entry_price = price
            self.active_trade = {
                "type": "LONG",
                "entry_time": format_time(current_time_ms),
                "entry_price": price,
                "entry_ema": f"{self.last_fast_ema:.2f}/{self.last_slow_ema:.2f}",
                "status": "OPEN",
                "logs": []
            }
            logger.info(f"ENTRY_LONG at {price:.2f}")
        
        elif action == "ENTRY_SHORT":
            self.current_position = -1
            self.last_entry_price = price
            self.active_trade = {
                "type": "SHORT",
                "entry_time": format_time(current_time_ms),
                "entry_price": price,
                "entry_ema": f"{self.last_fast_ema:.2f}/{self.last_slow_ema:.2f}",
                "status": "OPEN",
                "logs": []
            }
            logger.info(f"ENTRY_SHORT at {price:.2f}")
        
        elif action == "EXIT_LONG":
            self.current_position = 0
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["exit_ema"] = f"{self.last_fast_ema:.2f}/{self.last_slow_ema:.2f}"
                self.active_trade["status"] = "CLOSED"
                self.active_trade["points"] = price - self.active_trade["entry_price"]
                self.trades.append(self.active_trade)
                logger.info(f"EXIT_LONG at {price:.2f}, PnL: {self.active_trade['points']:.2f}")
                self.active_trade = None
            
            self.entry_price = None
        
        elif action == "EXIT_SHORT":
            self.current_position = 0
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["exit_ema"] = f"{self.last_fast_ema:.2f}/{self.last_slow_ema:.2f}"
                self.active_trade["status"] = "CLOSED"
                self.active_trade["points"] = self.active_trade["entry_price"] - price
                self.trades.append(self.active_trade)
                logger.info(f"EXIT_SHORT at {price:.2f}, PnL: {self.active_trade['points']:.2f}")
                self.active_trade = None
            
            self.entry_price = None
    
    def set_position(self, position: int):
        """Set the current position state."""
        self.current_position = position
    
    def reconcile_position(self, size: float, entry_price: float):
        """
        Reconcile internal state with exchange position.
        
        Args:
            size: Position size from exchange (positive for long, negative for short)
            entry_price: Entry price from exchange
        """
        import time
        import datetime
        
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms / 1000).strftime('%d-%m-%y %H:%M')
        
        expected_pos = 0
        if size > 0:
            expected_pos = 1
        elif size < 0:
            expected_pos = -1
        
        if self.current_position != expected_pos:
            logger.warning(f"Reconciling: Internal {self.current_position} -> Exchange {expected_pos} (Size: {size})")
            self.current_position = expected_pos
            
            if expected_pos != 0 and not self.active_trade:
                side = "LONG" if expected_pos == 1 else "SHORT"
                self.active_trade = {
                    "type": side,
                    "entry_time": format_time(time.time() * 1000) + " (Rec)",
                    "entry_price": entry_price,
                    "entry_ema": "-/-",
                    "status": "OPEN"
                }
                self.entry_price = entry_price
                logger.warning("Reconciled position - created active trade record")
            
            elif expected_pos == 0 and self.active_trade:
                self.active_trade["exit_time"] = format_time(time.time() * 1000) + " (Rec)"
                self.active_trade["status"] = "CLOSED (SYNC)"
                self.trades.append(self.active_trade)
                self.active_trade = None
                logger.warning("Reconciled position - closed active trade record")
    
    def run_backtest(self, df: pd.DataFrame):
        """
        Run backtest on historical data for strategy warmup.
        
        Args:
            df: DataFrame with historical OHLC data
        """
        logger.info("Starting EMA Cross backtest warmup...")
        self.trades = []
        self.current_position = 0
        self.active_trade = None
        self.entry_price = None
        
        if df.empty:
            return
        
        min_periods = max(self.fast_ema_length, self.slow_ema_length) + 1
        
        # Pre-calculate EMAs
        close = df['close'].astype(float)
        fast_ema_series = close.ewm(span=self.fast_ema_length, adjust=False).mean()
        slow_ema_series = close.ewm(span=self.slow_ema_length, adjust=False).mean()
        
        for i in range(len(df)):
            if i < min_periods:
                continue
            
            current_time_ms = df['time'].iloc[i] * 1000
            current_close = df['close'].iloc[i]
            
            fast_ema = fast_ema_series.iloc[i]
            slow_ema = slow_ema_series.iloc[i]
            fast_prev = fast_ema_series.iloc[i - 1]
            slow_prev = slow_ema_series.iloc[i - 1]
            
            if pd.isna(fast_ema) or pd.isna(slow_ema):
                continue
            
            # Detect Crossovers
            bullish_cross = (fast_prev <= slow_prev) and (fast_ema > slow_ema)
            bearish_cross = (fast_prev >= slow_prev) and (fast_ema < slow_ema)
            
            # Cache EMA values
            self.last_fast_ema = fast_ema
            self.last_slow_ema = slow_ema
            
            # Signal Logic
            if self.current_position == 0:
                # Flat - look for entries
                if self.allow_long and bullish_cross:
                    self.update_position_state("ENTRY_LONG", current_time_ms, None, current_close)
                elif self.allow_short and bearish_cross:
                    self.update_position_state("ENTRY_SHORT", current_time_ms, None, current_close)
            
            elif self.current_position == 1:
                # Long - look for exit
                if bearish_cross:
                    self.update_position_state("EXIT_LONG", current_time_ms, None, current_close)
                    # Check for flip to short
                    if self.allow_flip and self.allow_short:
                        self.update_position_state("ENTRY_SHORT", current_time_ms, None, current_close)
            
            elif self.current_position == -1:
                # Short - look for exit
                if bullish_cross:
                    self.update_position_state("EXIT_SHORT", current_time_ms, None, current_close)
                    # Check for flip to long
                    if self.allow_flip and self.allow_long:
                        self.update_position_state("ENTRY_LONG", current_time_ms, None, current_close)
        
        logger.info(f"Backtest warmup complete. Trades: {len(self.trades)}")
