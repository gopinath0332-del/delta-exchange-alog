import logging
from typing import Dict, Optional, Tuple, Any
import pandas as pd
import ta
from core.config import get_config

logger = logging.getLogger(__name__)

class RSI50EMAStrategy:
    """
    RSI + 50 EMA Strategy for XRPUSD (1H).
    
    Logic:
    - Long Entry: Close > 50 EMA and RSI > 40
    - Long Exit: Close < 50 EMA
    
    Parameters:
    - EMA Length: 50
    - RSI Length: 14
    - RSI Entry Level: 40.0
    """
    
    def __init__(self):
        # Load Config
        config = get_config()
        cfg = config.settings.get("strategies", {}).get("rsi_50_ema", {})

        # Parameters
        self.ema_length = cfg.get("ema_length", 50)
        self.rsi_length = cfg.get("rsi_length", 14)
        self.rsi_entry_level = cfg.get("rsi_entry_level", 40.0)
        
        self.indicator_label = "RSI"
        
        # State
        self.current_position = 0  # 1 for Long, 0 for Flat
        self.last_entry_price = 0.0
        
        # Indicator Cache (for dashboard)
        self.last_rsi = 0.0
        self.last_ema = 0.0
        
        # Trade History
        self.trades = []
        self.active_trade = None
        
    def calculate_indicators(self, df: pd.DataFrame, current_time: Optional[float] = None) -> Tuple[float, float]:
        """
        Calculate RSI and EMA for the given dataframe.
        Expected columns: 'close'
        """
        try:
            # Ensure we have enough data
            if len(df) < max(self.rsi_length, self.ema_length) + 1:
                return 0.0, 0.0
                
            if current_time is None:
                import time
                current_time = time.time()
                
            # EMA
            ema_series = ta.trend.ema_indicator(df['close'], window=self.ema_length)
            
            # RSI
            rsi_series = ta.momentum.rsi(df['close'], window=self.rsi_length)
            
            current_ema = ema_series.iloc[-1]
            current_rsi = rsi_series.iloc[-1]
            
            # Cache for dashboard (Live)
            self.last_ema = current_ema
            self.last_rsi = current_rsi
            
            # Dynamic Closed Candle Logic
            last_candle_ts = df['time'].iloc[-1]
            # Handle potential ms timestamp
            if last_candle_ts > 1e11: last_candle_ts /= 1000
            
            diff = current_time - last_candle_ts
            
            # If diff >= 3600 (1h), the last candle IS the closed candle (new one hasn't appeared)
            # If diff < 3600, the last candle is developing, so -2 is the closed one
            closed_idx = -1 if diff >= 3600 else -2
            
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
            
            return current_rsi, current_ema
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return 0.0, 0.0

    def check_signals(self, df: pd.DataFrame, current_time_ms: float) -> Tuple[Optional[str], str]:
        """
        Check for entry/exit signals.
        """
        if df.empty:
            return None, ""
            
        if len(df) < 2:
            return None, ""

        # Get indicators (Pass current time for dynamic logic)
        current_time_s = current_time_ms / 1000.0
        rsi, ema = self.calculate_indicators(df, current_time=current_time_s)
        
        # Determine which index to use for SIGNALS
        # Same logic as calculate_indicators
        last_candle_ts = df['time'].iloc[-1]
        if last_candle_ts > 1e11: last_candle_ts /= 1000
        
        diff = current_time_s - last_candle_ts
        closed_idx = -1 if diff >= 3600 else -2
        
        if closed_idx == -1:
             logger.debug(f"Using Index -1 as Closed Candle (Diff: {diff:.0f}s)")
        
        # We need the closed price at the determined index
        close_closed = df['close'].iloc[closed_idx]
        rsi_closed = self.last_closed_rsi
        ema_closed = self.last_closed_ema
        
        # Determine if we should treat this as a signal that happened "just now" (at close of candle)
        # In live run, this function is called on the developing candle.
        # If the *previous* candle closed with a signal, we enter NOW (Market).
        
        action = None
        reason = ""
        
        # --- Logic ---
        
        # Entry Long
        # Condition: Close > EMA50 AND RSI > 40 AND Not in Position
        if self.current_position == 0:
            # Fresh Signal Check:
            # Condition met NOW (closed_idx) AND Condition NOT met BEFORE (closed_idx - 1)
            # This prevents entering mid-trend on restart.
            
            prev_idx = closed_idx - 1

            # Rerun indicators as series here for safety and lookback
            ema_series = ta.trend.ema_indicator(df['close'], window=self.ema_length)
            rsi_series = ta.momentum.rsi(df['close'], window=self.rsi_length)
            
            # Index [closed_idx] (Last Closed)
            c_2 = df['close'].iloc[closed_idx]
            ema_2 = ema_series.iloc[closed_idx]
            rsi_2 = rsi_series.iloc[closed_idx]
            
            # Index [prev_idx] (Previous to Last Closed)
            c_3 = df['close'].iloc[prev_idx]
            ema_3 = ema_series.iloc[prev_idx]
            rsi_3 = rsi_series.iloc[prev_idx]
            
            is_valid_now = (c_2 > ema_2) and (rsi_2 > self.rsi_entry_level)
            was_valid_prev = (c_3 > ema_3) and (rsi_3 > self.rsi_entry_level)
            
            if is_valid_now and not was_valid_prev:
                action = "ENTRY_LONG"
                reason = f"Fresh Entry Signal: Close {c_2:.2f} > EMA {ema_2:.2f} & RSI {rsi_2:.2f} > {self.rsi_entry_level} (Prev: {was_valid_prev})"
                
        # Exit Long
        # Condition: Close < EMA50
        elif self.current_position == 1:
            if close_closed < ema_closed:
                action = "EXIT_LONG"
                reason = f"Exit Signal (Closed Candle): Close {close_closed:.2f} < EMA {ema_closed:.2f}"
                
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
                "status": "OPEN",
                "logs": []
            }
            
        elif action == "EXIT_LONG":
            self.current_position = 0
            
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["exit_rsi"] = rsi
                self.active_trade["status"] = "CLOSED"
                self.trades.append(self.active_trade)
                self.active_trade = None

    def reconcile_position(self, size: float, entry_price: float):
        """Reconcile state with exchange."""
        if size > 0:
            if self.current_position != 1:
                self.current_position = 1
                self.last_entry_price = entry_price
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
        
        if df.empty: return

        # Pre-calc indicators for speed
        ema_series = ta.trend.ema_indicator(df['close'], window=self.ema_length)
        rsi_series = ta.momentum.rsi(df['close'], window=self.rsi_length)
        
        for i in range(len(df)):
            if i < self.ema_length: continue
            
            current_time_s = df['time'].iloc[i]
            current_time_ms = current_time_s * 1000
            
            close = df['close'].iloc[i]
            
            ema = ema_series.iloc[i]
            rsi = rsi_series.iloc[i]
            
            if pd.isna(ema) or pd.isna(rsi): continue
            
            # --- Logic ---
            action = None
            
            # Use Index i-1 (Previous Closed Candle) for Signal
            # We are currently at time i (Entry/Action Time)
            # Conditions must be met at i-1
            
            prev_close = df['close'].iloc[i-1]
            prev_ema = ema_series.iloc[i-1]
            prev_rsi = rsi_series.iloc[i-1]
            
            if self.current_position == 0:
                if (prev_close > prev_ema) and (prev_rsi > self.rsi_entry_level):
                    action = "ENTRY_LONG"
                    
            elif self.current_position == 1:
                if prev_close < prev_ema:
                    action = "EXIT_LONG"
            
            if action:
                self.update_position_state(action, current_time_ms, prev_rsi, close)
                
        logger.info(f"Backtest complete. Trades: {len(self.trades)}")
