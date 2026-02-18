import logging
from typing import Dict, Optional, Tuple, Any
import pandas as pd
import ta
from core.config import get_config

logger = logging.getLogger(__name__)

class RSI200EMAStrategy:
    """
    RSI + 200 EMA Strategy for ETHUSD (3H) with Partial TP and ATR Trailing Stop.
    
    Logic:
    - Long Entry: RSI crossover above 70 AND close > 200 EMA
    - Partial TP: 50% exit at entry + (ATR * 2.5)
    - Trailing Stop: close - (ATR * 2.5), updates dynamically
    - Long Exit: RSI crossunder below 35 OR close < 200 EMA OR trailing stop hit
    
    Parameters (from Pine Script):
    - RSI Length: 17
    - RSI Entry Level: 70
    - RSI Exit Level: 35
    - EMA Length: 200
    - ATR Length: 17
    - ATR Multiplier for TP: 2.5
    - ATR Multiplier for Trailing SL: 2.5
    """
    
    def __init__(self):
        # Load Config
        config = get_config()
        cfg = config.settings.get("strategies", {}).get("rsi_200_ema", {})

        # Parameters
        self.rsi_length = cfg.get("rsi_length", 17)
        self.rsi_entry_level = cfg.get("rsi_entry_level", 70)
        self.rsi_exit_level = cfg.get("rsi_exit_level", 35)
        self.ema_length = cfg.get("ema_length", 200)
        self.atr_length = cfg.get("atr_length", 17)
        self.atr_multiplier_tp = cfg.get("atr_multiplier_tp", 2.5)
        self.atr_multiplier_trail = cfg.get("atr_multiplier_trail", 2.5)
        self.enable_partial_tp = cfg.get("enable_partial_tp", True)  # Overridden per-coin from .env by runner
        self.partial_pct = cfg.get("partial_pct", 0.5)
        
        self.indicator_label = "RSI"
        
        # Timeframe (set by runner, defaults to 1h)
        self.timeframe = "1h"
        
        # State
        self.current_position = 0  # 1 for Long, 0 for Flat
        self.last_entry_price = 0.0
        self.entry_price = None  # Entry price for current position
        self.tp_level = None  # Take profit level
        self.trailing_stop_level = None  # Trailing stop level
        self.partial_exit_done = False  # Flag for partial exit
        
        # Indicator Cache (for dashboard)
        self.last_rsi = 0.0
        self.last_ema = 0.0
        self.last_atr = 0.0
        
        # Trade History
        self.trades = []
        self.active_trade = None
        
        # For closed candle tracking
        self.last_closed_time_str = "-"
        self.last_closed_rsi = 0.0
        self.last_closed_ema = 0.0
        
    def calculate_indicators(self, df: pd.DataFrame, current_time: Optional[float] = None) -> Tuple[float, float, float]:
        """
        Calculate RSI, EMA, and ATR for the given dataframe.
        Expected columns: 'close', 'high', 'low'
        """
        try:
            # Ensure we have enough data
            if len(df) < max(self.rsi_length, self.ema_length, self.atr_length) + 1:
                return 0.0, 0.0, 0.0
                
            if current_time is None:
                import time
                current_time = time.time()
                
            # EMA
            ema_series = ta.trend.ema_indicator(df['close'], window=self.ema_length)
            
            # RSI
            rsi_series = ta.momentum.rsi(df['close'], window=self.rsi_length)
            
            # ATR
            atr_series = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.atr_length)
            
            current_ema = ema_series.iloc[-1]
            current_rsi = rsi_series.iloc[-1]
            current_atr = atr_series.iloc[-1]
            
            # Cache for dashboard (Live)
            self.last_ema = current_ema
            self.last_rsi = current_rsi
            self.last_atr = current_atr
            
            # Dynamic Closed Candle Logic (for 3-hour candles)
            last_candle_ts = df['time'].iloc[-1]
            # Handle potential ms timestamp
            if last_candle_ts > 1e11: last_candle_ts /= 1000
            
            diff = current_time - last_candle_ts
            
            # If diff >= 10800 (3h), the last candle IS the closed candle (new one hasn't appeared)
            # If diff < 10800, the last candle is developing, so -2 is the closed one
            closed_idx = -1 if diff >= 10800 else -2
            
            # Cache Last Closed Candle
            if len(df) >= abs(closed_idx):
                import datetime
                ts = df['time'].iloc[closed_idx]
                if ts > 1e11: ts /= 1000
                self.last_closed_time_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M')
                self.last_closed_ema = ema_series.iloc[closed_idx]
                self.last_closed_rsi = rsi_series.iloc[closed_idx]
            else:
                self.last_closed_time_str = "-"
                self.last_closed_ema = 0.0
                self.last_closed_rsi = 0.0
            
            return current_rsi, current_ema, current_atr
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return 0.0, 0.0, 0.0

    def check_signals(self, df: pd.DataFrame, current_time_ms: float) -> Tuple[Optional[str], str]:
        """
        Check for entry/exit signals.
        """
        if df.empty:
            return None, ""
            
        if len(df) < 3:  # Need at least 3 candles for crossover detection
            return None, ""

        # Get indicators (Pass current time for dynamic logic)
        current_time_s = current_time_ms / 1000.0
        rsi, ema, atr = self.calculate_indicators(df, current_time=current_time_s)
        
        # Determine which index to use for SIGNALS
        # Same logic as calculate_indicators
        last_candle_ts = df['time'].iloc[-1]
        if last_candle_ts > 1e11: last_candle_ts /= 1000
        
        diff = current_time_s - last_candle_ts
        closed_idx = -1 if diff >= 10800 else -2
        
        if closed_idx == -1:
             logger.debug(f"Using Index -1 as Closed Candle (Diff: {diff:.0f}s)")
        
        # We need the closed price at the determined index
        close_closed = df['close'].iloc[closed_idx]
        rsi_closed = self.last_closed_rsi
        ema_closed = self.last_closed_ema
        
        # Get current price for stop/tp checks
        current_price = df['close'].iloc[-1]
        
        action = None
        reason = ""
        
        # --- Logic ---
        
        # Update Trailing Stop if in position
        if self.current_position == 1 and self.trailing_stop_level is not None:
            new_stop = current_price - (atr * self.atr_multiplier_trail)
            if new_stop > self.trailing_stop_level:
                self.trailing_stop_level = new_stop
                logger.debug(f"Updated trailing stop to {new_stop:.2f}")
        
        # Check Trailing Stop Hit
        if self.current_position == 1 and self.trailing_stop_level is not None:
            if current_price < self.trailing_stop_level:
                action = "EXIT_LONG"
                reason = f"Trailing SL Hit: Price {current_price:.2f} < Stop {self.trailing_stop_level:.2f}"
                return action, reason
        
        # Check Partial TP
        if self.enable_partial_tp and self.current_position == 1 and not self.partial_exit_done and self.tp_level is not None:
            if current_price >= self.tp_level:
                action = "PARTIAL_EXIT"
                reason = f"Partial TP Hit: Price {current_price:.2f} >= TP {self.tp_level:.2f}"
                return action, reason
        
        # Entry Long
        # Condition: RSI crossover 70 AND Close > EMA200 AND Not in Position
        if self.current_position == 0:
            # Recalculate indicators as series for crossover detection
            ema_series = ta.trend.ema_indicator(df['close'], window=self.ema_length)
            rsi_series = ta.momentum.rsi(df['close'], window=self.rsi_length)
            atr_series = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.atr_length)
            
            # Index [closed_idx] (Last Closed)
            c_now = df['close'].iloc[closed_idx]
            ema_now = ema_series.iloc[closed_idx]
            rsi_now = rsi_series.iloc[closed_idx]
            atr_now = atr_series.iloc[closed_idx]
            
            # Index [prev_idx] (Previous to Last Closed)
            prev_idx = closed_idx - 1
            rsi_prev = rsi_series.iloc[prev_idx]
            
            # Crossover: RSI was <= 70 before and is > 70 now
            rsi_crossover = (rsi_prev <= self.rsi_entry_level) and (rsi_now > self.rsi_entry_level)
            close_above_ema = c_now > ema_now
            
            if rsi_crossover and close_above_ema:
                action = "ENTRY_LONG"
                reason = f"Entry Signal: RSI crossover {self.rsi_entry_level} ({rsi_prev:.2f} -> {rsi_now:.2f}) & Close {c_now:.2f} > EMA {ema_now:.2f}"
                
                # Set TP and Trailing Stop levels
                self.entry_price = close_closed
                self.tp_level = close_closed + (atr_now * self.atr_multiplier_tp)
                self.trailing_stop_level = close_closed - (atr_now * self.atr_multiplier_trail)
                self.partial_exit_done = False
                
        # Exit Long
        # Condition: RSI crossunder 35 OR Close < EMA200
        elif self.current_position == 1:
            # Recalculate for crossunder detection
            ema_series = ta.trend.ema_indicator(df['close'], window=self.ema_length)
            rsi_series = ta.momentum.rsi(df['close'], window=self.rsi_length)
            
            c_now = df['close'].iloc[closed_idx]
            ema_now = ema_series.iloc[closed_idx]
            rsi_now = rsi_series.iloc[closed_idx]
            
            prev_idx = closed_idx - 1
            rsi_prev = rsi_series.iloc[prev_idx]
            
            # Crossunder: RSI was >= 35 before and is < 35 now
            rsi_crossunder = (rsi_prev >= self.rsi_exit_level) and (rsi_now < self.rsi_exit_level)
            close_below_ema = c_now < ema_now
            
            if rsi_crossunder:
                action = "EXIT_LONG"
                reason = f"Exit Signal: RSI crossunder {self.rsi_exit_level} ({rsi_prev:.2f} -> {rsi_now:.2f})"
            elif close_below_ema:
                action = "EXIT_LONG"
                reason = f"Exit Signal: Close {c_now:.2f} < EMA {ema_now:.2f}"
                
        return action, reason

    def update_position_state(self, action: str, current_time_ms: float, indicators: Any = None, price: float = 0.0, reason: str = ""):
        """Update internal state based on executed action."""
        import datetime
        
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')
            
        # Handle indicators argument being float (legacy) or dict/other
        rsi = 0.0
        if isinstance(indicators, dict):
             rsi = indicators.get('rsi', 0.0)
        elif isinstance(indicators, (float, int)):
             rsi = indicators
        
        if action == "ENTRY_LONG":
            self.current_position = 1
            self.last_entry_price = price
            
            self.active_trade = {
                "type": "LONG",
                "entry_time": format_time(current_time_ms),
                "entry_price": price,
                "entry_rsi": rsi,
                "exit_time": None,
                "exit_price": None,
                "exit_rsi": None,
                "status": "OPEN",
                "partial_exit": False,
                "logs": []
            }
            
        elif action == "PARTIAL_EXIT":
            # Record partial exit in trade history
            if self.active_trade:
                # Create a copy for the partial exit record
                partial_trade = self.active_trade.copy()
                partial_trade["exit_time"] = format_time(current_time_ms)
                partial_trade["exit_price"] = price
                partial_trade["exit_rsi"] = rsi
                partial_trade["status"] = "PARTIAL"
                partial_trade["points"] = price - partial_trade["entry_price"]
                self.trades.append(partial_trade)
                
                # Mark partial exit done
                self.partial_exit_done = True
                self.active_trade["partial_exit"] = True
                
        elif action == "EXIT_LONG":
            self.current_position = 0
            
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["exit_rsi"] = rsi
                
                # Determine exit reason for status
                if "Trailing SL" in reason:
                    self.active_trade["status"] = "TRAIL STOP"
                elif "RSI" in reason:
                    self.active_trade["status"] = "RSI EXIT"
                elif "EMA" in reason:
                    self.active_trade["status"] = "EMA EXIT"
                else:
                    self.active_trade["status"] = "CLOSED"
                    
                self.active_trade["points"] = price - self.active_trade["entry_price"]
                self.trades.append(self.active_trade)
                self.active_trade = None
            
            # Reset levels
            self.entry_price = None
            self.tp_level = None
            self.trailing_stop_level = None
            self.partial_exit_done = False

    def reconcile_position(self, size: float, entry_price: float):
        """Reconcile state with exchange."""
        if size > 0:
            if self.current_position != 1:
                self.current_position = 1
                self.last_entry_price = entry_price
                self.entry_price = entry_price
                logger.info(f"Reconciled state to LONG (Size: {size})")
        elif size == 0:
            if self.current_position != 0:
                self.current_position = 0
                logger.info("Reconciled state to FLAT")
                
            # Ensure active_trade is closed if we are actually FLAT
            if self.active_trade:
                import time
                current_timestamp = time.time() * 1000
                import datetime
                formatted_time = datetime.datetime.fromtimestamp(current_timestamp/1000).strftime('%d-%m-%y %H:%M')
                
                logger.info("Closing phantom active_trade via Reconciliation")
                self.active_trade["exit_time"] = f"{formatted_time} (Reconciled)"
                self.active_trade["exit_price"] = 0.0 # Unknown or fetch if possible, but 0 tells us it's special
                self.active_trade["exit_rsi"] = 0.0
                self.active_trade["status"] = "CLOSED (SYNC)"
                self.trades.append(self.active_trade)
                self.active_trade = None

    def run_backtest(self, df: pd.DataFrame):
        """Simple backtest loop."""
        self.trades = []
        self.current_position = 0
        self.active_trade = None
        self.entry_price = None
        self.tp_level = None
        self.trailing_stop_level = None
        self.partial_exit_done = False
        
        if df.empty: return

        # Pre-calc indicators for speed
        ema_series = ta.trend.ema_indicator(df['close'], window=self.ema_length)
        rsi_series = ta.momentum.rsi(df['close'], window=self.rsi_length)
        atr_series = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.atr_length)
        
        for i in range(len(df)):
            if i < max(self.ema_length, self.rsi_length, self.atr_length) + 1: continue
            
            current_time_s = df['time'].iloc[i]
            current_time_ms = current_time_s * 1000
            
            close = df['close'].iloc[i]
            
            ema = ema_series.iloc[i]
            rsi = rsi_series.iloc[i]
            atr = atr_series.iloc[i]
            
            if pd.isna(ema) or pd.isna(rsi) or pd.isna(atr): continue
            
            # Update Trailing Stop
            if self.current_position == 1 and self.trailing_stop_level is not None:
                new_stop = close - (atr * self.atr_multiplier_trail)
                if new_stop > self.trailing_stop_level:
                    self.trailing_stop_level = new_stop
            
            # Check Trailing Stop Hit
            if self.current_position == 1 and self.trailing_stop_level is not None:
                if close < self.trailing_stop_level:
                    self.update_position_state("EXIT_LONG", current_time_ms, rsi, close, "Trailing SL Hit")
                    continue
            
            # Check Partial TP
            if self.enable_partial_tp and self.current_position == 1 and not self.partial_exit_done and self.tp_level is not None:
                if close >= self.tp_level:
                    self.update_position_state("PARTIAL_EXIT", current_time_ms, rsi, close, "Partial TP Hit")
                    # Continue to check for other signals
            
            # --- Logic ---
            action = None
            
            # Use Index i-1 (Previous Closed Candle) for Signal
            # We are currently at time i (Entry/Action Time)
            # Conditions must be met at i-1
            
            prev_close = df['close'].iloc[i-1]
            prev_ema = ema_series.iloc[i-1]
            prev_rsi = rsi_series.iloc[i-1]
            prev_atr = atr_series.iloc[i-1]
            
            # Get i-2 for crossover detection
            prev2_rsi = rsi_series.iloc[i-2] if i >= 2 else 0
            
            if self.current_position == 0:
                # Entry: RSI crossover 70 AND close > EMA
                rsi_crossover = (prev2_rsi <= self.rsi_entry_level) and (prev_rsi > self.rsi_entry_level)
                close_above_ema = prev_close > prev_ema
                
                if rsi_crossover and close_above_ema:
                    action = "ENTRY_LONG"
                    # Set levels
                    self.entry_price = close
                    self.tp_level = close + (prev_atr * self.atr_multiplier_tp)
                    self.trailing_stop_level = close - (prev_atr * self.atr_multiplier_trail)
                    self.partial_exit_done = False
                    
            elif self.current_position == 1:
                # Exit: RSI crossunder 35 OR close < EMA
                rsi_crossunder = (prev2_rsi >= self.rsi_exit_level) and (prev_rsi < self.rsi_exit_level)
                close_below_ema = prev_close < prev_ema
                
                if rsi_crossunder or close_below_ema:
                    action = "EXIT_LONG"
            
            if action:
                reason = "RSI Exit" if action == "EXIT_LONG" else "Entry"
                self.update_position_state(action, current_time_ms, prev_rsi, close, reason)
                
        logger.info(f"Backtest complete. Trades: {len(self.trades)}")
