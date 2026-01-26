import logging
from typing import Optional, Tuple, Any
import pandas as pd
import numpy as np
import ta
from core.config import get_config

logger = logging.getLogger(__name__)

class RSISupertrendStrategy:
    """
    RSI with Supertrend Strategy for RIVERUSD (1H Standard Candles).
    
    This is a LONG-ONLY strategy based on Pine Script implementation.
    
    Logic:
    - Long Entry: RSI crosses above entry level (default 50)
    - Long Exit: Supertrend flips from bullish (dir < 0) to bearish (dir > 0)
    
    Parameters:
    - RSI Length: 14
    - RSI Long Entry Level: 50.0
    - Supertrend ATR Length: 10
    - Supertrend Multiplier: 2.0
    """
    
    def __init__(self):
        """Initialize the RSI-Supertrend strategy with configuration parameters."""
        # Load Config
        config = get_config()
        cfg = config.settings.get("strategies", {}).get("rsi_supertrend", {})

        # RSI Parameters
        self.rsi_length = cfg.get("rsi_length", 14)
        self.rsi_long_level = cfg.get("rsi_long_level", 50.0)
        
        # Supertrend Parameters
        self.atr_length = cfg.get("atr_length", 10)
        self.atr_multiplier = cfg.get("atr_multiplier", 2.0)
        
        self.indicator_label = "RSI"
        
        # Timeframe (set by runner, defaults to 1h)
        self.timeframe = "1h"
        
        # State
        self.current_position = 0  # 1 for Long, 0 for Flat
        self.last_entry_price = 0.0
        
        # Indicator Cache (for dashboard)
        self.last_rsi = 0.0
        self.last_supertrend = 0.0
        self.last_supertrend_dir = 0
        
        # Closed candle cache
        self.last_closed_time_str = "-"
        self.last_closed_rsi = 0.0
        self.last_closed_supertrend = 0.0
        self.last_closed_supertrend_dir = 0
        
        # Trade History
        self.trades = []
        self.active_trade = None
        
    def calculate_supertrend(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        Calculate Supertrend indicator matching Pine Script's ta.supertrend() logic.
        
        Returns:
        - supertrend: The Supertrend line values
        - direction: -1 for bullish (green), 1 for bearish (red)
        """
        try:
            # Extract OHLC data
            high = df['high'].astype(float).values
            low = df['low'].astype(float).values
            close = df['close'].astype(float).values
            n = len(df)
            
            # Calculate True Range
            tr = np.zeros(n)
            tr[0] = high[0] - low[0]
            for i in range(1, n):
                hl = high[i] - low[i]
                hc = abs(high[i] - close[i-1])
                lc = abs(low[i] - close[i-1])
                tr[i] = max(hl, hc, lc)
            
            # Calculate ATR using RMA (Running Moving Average / Wilder's smoothing)
            # Pine Script's ta.supertrend() uses RMA, not SMA
            # RMA formula: RMA[i] = (RMA[i-1] * (length - 1) + value[i]) / length
            atr = np.zeros(n)
            # Initialize first ATR with SMA of first 'atr_length' values
            atr[self.atr_length - 1] = np.mean(tr[:self.atr_length])
            
            # Calculate RMA for the rest
            for i in range(self.atr_length, n):
                atr[i] = (atr[i-1] * (self.atr_length - 1) + tr[i]) / self.atr_length
            
            # For values before atr_length, use expanding mean
            for i in range(self.atr_length - 1):
                atr[i] = np.mean(tr[:i+1])
            
            # Calculate HL2 (High + Low) / 2
            hl2 = (high + low) / 2.0
            
            # Calculate basic upper and lower bands
            basic_ub = hl2 + (self.atr_multiplier * atr)
            basic_lb = hl2 - (self.atr_multiplier * atr)
            
            # Initialize final bands
            final_ub = np.zeros(n)
            final_lb = np.zeros(n)
            final_ub[0] = basic_ub[0]
            final_lb[0] = basic_lb[0]
            
            # Calculate final bands with persistence
            for i in range(1, n):
                # Upper Band: use basic_ub[i] if it's less than previous final_ub OR if close breached upper band
                if basic_ub[i] < final_ub[i-1] or close[i-1] > final_ub[i-1]:
                    final_ub[i] = basic_ub[i]
                else:
                    final_ub[i] = final_ub[i-1]
                
                # Lower Band: use basic_lb[i] if it's greater than previous final_lb OR if close breached lower band
                if basic_lb[i] > final_lb[i-1] or close[i-1] < final_lb[i-1]:
                    final_lb[i] = basic_lb[i]
                else:
                    final_lb[i] = final_lb[i-1]
            
            # Determine Supertrend and Direction
            supertrend = np.zeros(n)
            direction = np.zeros(n, dtype=int)
            
            # Initialize first direction based on close position
            if close[0] <= final_ub[0]:
                direction[0] = 1  # Bearish
                supertrend[0] = final_ub[0]
            else:
                direction[0] = -1  # Bullish
                supertrend[0] = final_lb[0]
            
            # Calculate direction and supertrend for rest of series
            for i in range(1, n):
                # Direction change logic matching Pine Script
                if direction[i-1] == -1:  # Was bullish
                    # Stay bullish as long as close stays above lower band
                    if close[i] > final_lb[i]:
                        direction[i] = -1
                        supertrend[i] = final_lb[i]
                    else:
                        # Flip to bearish
                        direction[i] = 1
                        supertrend[i] = final_ub[i]
                else:  # Was bearish (direction[i-1] == 1)
                    # Stay bearish as long as close stays below upper band
                    if close[i] < final_ub[i]:
                        direction[i] = 1
                        supertrend[i] = final_ub[i]
                    else:
                        # Flip to bullish
                        direction[i] = -1
                        supertrend[i] = final_lb[i]
            
            return pd.Series(supertrend, index=df.index), pd.Series(direction, index=df.index)
            
        except Exception as e:
            logger.error("Error calculating Supertrend: %s", str(e))
            return pd.Series([0.0] * len(df), index=df.index), pd.Series([0] * len(df), index=df.index)
    
    def calculate_indicators(self, df: pd.DataFrame, current_time: Optional[float] = None) -> Tuple[float, float, int]:
        """
        Calculate RSI and Supertrend for the given dataframe.
        
        Expected columns: 'open', 'high', 'low', 'close', 'time'
        
        Returns:
        - current_rsi: Current RSI value
        - current_supertrend: Current Supertrend value
        - current_direction: Current Supertrend direction (-1 bullish, 1 bearish)
        """
        try:
            # Ensure we have enough data
            min_required = max(self.rsi_length, self.atr_length) + 1
            if len(df) < min_required:
                return 0.0, 0.0, 0
                
            if current_time is None:
                import time
                current_time = time.time()
                
            # Calculate RSI
            rsi_series = ta.momentum.rsi(df['close'], window=self.rsi_length)
            
            # Calculate Supertrend
            supertrend_series, direction_series = self.calculate_supertrend(df)
            
            # Get current values
            current_rsi = rsi_series.iloc[-1]
            current_supertrend = supertrend_series.iloc[-1]
            current_direction = direction_series.iloc[-1]
            
            # Cache for dashboard (Live)
            self.last_rsi = current_rsi
            self.last_supertrend = current_supertrend
            self.last_supertrend_dir = current_direction
            
            # Dynamic Closed Candle Logic (for 1h timeframe)
            last_candle_ts = df['time'].iloc[-1]
            # Handle potential ms timestamp
            if last_candle_ts > 1e11:
                last_candle_ts /= 1000
            
            diff = current_time - last_candle_ts
            
            # If diff >= 3600 (1h), the last candle IS the closed candle (new one hasn't appeared)
            # If diff < 3600, the last candle is developing, so -2 is the closed one
            closed_idx = -1 if diff >= 3600 else -2
            
            # Cache Last Closed Candle
            if len(df) >= abs(closed_idx):
                import datetime
                ts = df['time'].iloc[closed_idx]
                if ts > 1e11:
                    ts /= 1000
                self.last_closed_time_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M')
                self.last_closed_rsi = rsi_series.iloc[closed_idx]
                self.last_closed_supertrend = supertrend_series.iloc[closed_idx]
                self.last_closed_supertrend_dir = direction_series.iloc[closed_idx]
            else:
                self.last_closed_time_str = "-"
                self.last_closed_rsi = 0.0
                self.last_closed_supertrend = 0.0
                self.last_closed_supertrend_dir = 0
            
            return current_rsi, current_supertrend, current_direction
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return 0.0, 0.0, 0

    def check_signals(self, df: pd.DataFrame, current_time_ms: float) -> Tuple[Optional[str], str]:
        """
        Check for entry/exit signals based on RSI crossover and Supertrend flip.
        
        Long Entry: RSI crosses above entry level
        Long Exit: Supertrend flips from bullish to bearish
        """
        if df.empty:
            return None, ""
            
        if len(df) < 2:
            return None, ""

        # Get indicators (Pass current time for dynamic logic)
        current_time_s = current_time_ms / 1000.0
        rsi, supertrend, direction = self.calculate_indicators(df, current_time=current_time_s)
        
        # Determine which index to use for SIGNALS
        # Same logic as calculate_indicators
        last_candle_ts = df['time'].iloc[-1]
        if last_candle_ts > 1e11:
            last_candle_ts /= 1000
        
        diff = current_time_s - last_candle_ts
        closed_idx = -1 if diff >= 3600 else -2
        
        if closed_idx == -1:
            logger.debug("Using Index -1 as Closed Candle (Diff: %d s)", diff)
        
        # Calculate indicator series for lookback
        rsi_series = ta.momentum.rsi(df['close'], window=self.rsi_length)
        supertrend_series, direction_series = self.calculate_supertrend(df)
        
        action = None
        reason = ""
        
        # --- Long Entry Logic ---
        if self.current_position == 0:
            # Fresh Signal Check: RSI crosses above entry level
            # Condition met NOW (closed_idx) AND Condition NOT met BEFORE (closed_idx - 1)
            # This prevents entering mid-trend on restart.
            
            prev_idx = closed_idx - 1
            
            # Current closed candle
            rsi_now = rsi_series.iloc[closed_idx]
            
            # Previous candle
            rsi_prev = rsi_series.iloc[prev_idx]
            
            # Crossover: prev <= level AND now > level
            is_crossover = (rsi_prev <= self.rsi_long_level) and (rsi_now > self.rsi_long_level)
            
            if is_crossover:
                action = "ENTRY_LONG"
                reason = f"Fresh Entry Signal: RSI crossed above {self.rsi_long_level} (Prev: {rsi_prev:.2f}, Now: {rsi_now:.2f})"
                
        # --- Long Exit Logic ---
        elif self.current_position == 1:
            # Exit when Supertrend flips from bullish (dir < 0) to bearish (dir > 0)
            prev_idx = closed_idx - 1
            
            dir_now = direction_series.iloc[closed_idx]
            dir_prev = direction_series.iloc[prev_idx]
            
            # Flip from bullish to bearish: prev was -1 (bullish) and now is 1 (bearish)
            supertrend_flip_bearish = (dir_prev < 0) and (dir_now > 0)
            
            if supertrend_flip_bearish:
                action = "EXIT_LONG"
                reason = "Exit Signal: Supertrend flipped from BULLISH to BEARISH"
                
        return action, reason

    def update_position_state(self, action: str, current_time_ms: float, indicators: Any = None, price: float = 0.0, reason: str = ""):  # pylint: disable=unused-argument
        """
        Update internal state based on executed action.
        
        Args:
            action: The action taken (ENTRY_LONG, EXIT_LONG)
            current_time_ms: Current timestamp in milliseconds
            indicators: RSI value or dict with indicator values
            price: Execution price
            reason: Reason for the action
        """
        import datetime
        
        def format_time(ts_ms):
            """Format timestamp to human-readable string."""
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
                "logs": []
            }
            
        elif action == "EXIT_LONG":
            self.current_position = 0
            
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["exit_rsi"] = rsi
                self.active_trade["status"] = "CLOSED"
                
                # Calculate points
                entry_price = self.active_trade.get("entry_price", 0.0)
                points = price - entry_price
                self.active_trade["points"] = points
                
                self.trades.append(self.active_trade)
                self.active_trade = None

    def reconcile_position(self, size: float, entry_price: float):
        """
        Reconcile strategy state with exchange position.
        
        Args:
            size: Position size from exchange (>0 for long, 0 for flat)
            entry_price: Entry price from exchange
        """
        if size > 0:
            if self.current_position != 1:
                self.current_position = 1
                self.last_entry_price = entry_price
                logger.info("Reconciled state to LONG (Size: %s, Entry: %s)", size, entry_price)
        elif size == 0:
            if self.current_position != 0:
                self.current_position = 0
                logger.info("Reconciled state to FLAT")
                
            # DO NOT close active_trade during reconciliation when FLAT
            # The trade is still logically open from strategy perspective
            # It will be properly closed when exit signal is triggered
            # This prevents showing negative P&L in trade history


    def run_backtest(self, df: pd.DataFrame):
        """
        Simple backtest loop for strategy warmup.
        
        Simulates the strategy on historical data to restore state.
        """
        self.trades = []
        self.current_position = 0
        self.active_trade = None
        
        if df.empty:
            return

        # Pre-calculate indicators for speed
        rsi_series = ta.momentum.rsi(df['close'], window=self.rsi_length)
        supertrend_series, direction_series = self.calculate_supertrend(df)
        
        min_required = max(self.rsi_length, self.atr_length) + 1
        
        for i in range(min_required, len(df)):
            current_time_s = df['time'].iloc[i]
            current_time_ms = current_time_s * 1000
            
            close = df['close'].iloc[i]
            
            rsi = rsi_series.iloc[i]
            direction = direction_series.iloc[i]
            
            if pd.isna(rsi) or pd.isna(direction):
                continue
            
            # --- Logic ---
            action = None
            
            # Use Index i-1 (Previous Closed Candle) for Signal
            # We are currently at time i (Entry/Action Time)
            # Conditions must be met at i-1
            
            prev_rsi = rsi_series.iloc[i-1]
            prev_prev_rsi = rsi_series.iloc[i-2]
            prev_direction = direction_series.iloc[i-1]
            prev_prev_direction = direction_series.iloc[i-2]
            
            # Long Entry: RSI crossover above entry level
            if self.current_position == 0:
                is_crossover = (prev_prev_rsi <= self.rsi_long_level) and (prev_rsi > self.rsi_long_level)
                
                if is_crossover:
                    action = "ENTRY_LONG"
                    
            # Long Exit: Supertrend flip from bullish to bearish
            elif self.current_position == 1:
                supertrend_flip = (prev_prev_direction < 0) and (prev_direction > 0)
                
                if supertrend_flip:
                    action = "EXIT_LONG"
            
            if action:
                self.update_position_state(action, current_time_ms, prev_rsi, close)
                
        logger.info("Backtest complete. Trades: %d", len(self.trades))
