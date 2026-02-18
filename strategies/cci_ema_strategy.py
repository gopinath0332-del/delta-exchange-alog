import logging
from typing import Dict, Optional, Tuple, Any

import pandas as pd
import ta
from core.config import get_config
from core.candle_utils import get_closed_candle_index

logger = logging.getLogger(__name__)

class CCIEMAStrategy:
    """
    CCI + 50 EMA Strategy for BTCUSD (1H).
    
    Logic:
    - Long Entry: CCI > 0 and Close > 50 EMA
    - Partial Exit (50%): Price >= Entry + (ATR * Multiplier)
    - Final Exit: CCI < 0 or Close < 50 EMA
    
    Parameters:
    - CCI Length: 30
    - EMA Length: 50
    - ATR Length: 20 (Updated from Pine script)
    - ATR Multiplier: 9.0 (Updated from Pine script for partial profit target)
    """
    
    def __init__(self):
        # Load Config
        config = get_config()
        cfg = config.settings.get("strategies", {}).get("cci_ema", {})
        
        # Parameters (defaults match Pine script: atrLength=20, atrTarget=9.0)
        self.cci_length = cfg.get("cci_length", 30)
        self.ema_length = cfg.get("ema_length", 50)
        self.atr_length = cfg.get("atr_length", 20)  # Updated from 14 to match Pine
        self.atr_multiplier = cfg.get("atr_multiplier", 9.0)  # Updated from 4.0 to match Pine
        self.enable_partial_tp = cfg.get("enable_partial_tp", True)  # Overridden per-coin from .env by runner
        self.partial_pct = cfg.get("partial_pct", 0.5)  # 50% partial exit when enabled
        
        self.indicator_label = "CCI"
        
        # Timeframe (set by runner, defaults to 1h)
        self.timeframe = "1h"
        
        # State
        self.current_position = 0  # 1 for Long, 0 for Flat
        self.last_entry_price = 0.0
        self.partial_profit_taken = False
        
        # Indicator Cache (for dashboard)
        self.last_cci = 0.0
        self.last_ema = 0.0
        self.last_atr = 0.0
        
        # Trade History
        self.trades = []
        self.active_trade = None
        
    def calculate_indicators(self, df: pd.DataFrame) -> Tuple[float, float, float]:
        """
        Calculate CCI, EMA, and ATR for the given dataframe.
        Expected columns: 'high', 'low', 'close'
        """
        try:
            # Ensure we have enough data
            if len(df) < max(self.cci_length, self.ema_length) + 1:
                return 0.0, 0.0, 0.0
                
            # CCI
            cci_series = ta.trend.cci(df['high'], df['low'], df['close'], window=self.cci_length)
            
            # EMA
            ema_series = ta.trend.ema_indicator(df['close'], window=self.ema_length)
            
            # ATR (Uses High, Low, Close)
            atr_series = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.atr_length)
            
            current_cci = cci_series.iloc[-1]
            current_ema = ema_series.iloc[-1]
            current_atr = atr_series.iloc[-1]
            
            current_atr = atr_series.iloc[-1]
            
            # Cache for dashboard (Live)
            self.last_cci = current_cci
            self.last_ema = current_ema
            self.last_atr = current_atr
            
            # Cache Last Closed Candle (Index -2)
            if len(df) >= 2:
                import datetime
                ts = df['time'].iloc[-2]
                if ts > 1e10: ts = ts / 1000 # Handle ms if needed
                self.last_closed_time_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M')
                self.last_closed_cci = cci_series.iloc[-2]
                self.last_closed_ema = ema_series.iloc[-2]
            else:
                self.last_closed_time_str = "-"
                self.last_closed_cci = 0.0
                self.last_closed_ema = 0.0
            
            return current_cci, current_ema, current_atr
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return 0.0, 0.0, 0.0

    def calculate_prev_cci(self, df: pd.DataFrame) -> Optional[float]:
        """Calculate CCI for the previous candle (index -2)."""
        if len(df) < self.cci_length + 2:
            return None
        try:
            # We need to calc series again? Or just slice properly
            # Optimization: pass existing series if possible, but here we just recalc for safety
            # Recalculating whole series is inefficient but safe.
            cci_series = ta.trend.cci(df['high'], df['low'], df['close'], window=self.cci_length)
            return cci_series.iloc[-2]
        except:
            return None

    def check_signals(self, df: pd.DataFrame, current_time_ms: float) -> Tuple[str, str]:
        """
        Check for entry/exit signals based on CLOSED candle data.
        
        Uses closed candle logic to match backtesting behavior and prevent
        false signals from developing candles.
        """
        if df.empty:
            return None, ""
        
        # Get Closed Candle Index
        closed_idx = get_closed_candle_index(df, current_time_ms, self.timeframe)
        
        # Get indicators for both closed and current candle
        cci, ema, atr = self.calculate_indicators(df)
        
        # Get CLOSED candle data for signal generation
        closed_candle = df.iloc[closed_idx]
        closed_price = closed_candle['close']
        
        # Get current candle high for partial exit check (real-time)
        current_high = df['high'].iloc[-1]
        
        # Recalculate indicators as series for crossover detection
        cci_series = ta.trend.cci(df['high'], df['low'], df['close'], window=self.cci_length)
        ema_series = ta.trend.ema_indicator(df['close'], window=self.ema_length)
        
        # Get closed candle indicator values
        closed_cci = cci_series.iloc[closed_idx]
        closed_ema = ema_series.iloc[closed_idx]
        
        action = None
        reason = ""
        
        # --- Logic ---
        
        # Trend Filter: Closed Price > EMA
        trend_bullish = closed_price > closed_ema
        
        # Entry Long
        # Condition: CCI CrossOver 0 AND Trend Bullish (on closed candle)
        if self.current_position == 0:
            # Get previous closed candle CCI for crossover check
            prev_closed_idx = closed_idx - 1
            if len(df) > abs(prev_closed_idx):
                prev_cci = cci_series.iloc[prev_closed_idx]
                # Crossover: Prev <= 0 AND Curr > 0
                cci_cross = (prev_cci <= 0) and (closed_cci > 0)
                if cci_cross and trend_bullish:
                    action = "ENTRY_LONG"
                    reason = f"CCI Cross {prev_cci:.2f}->{closed_cci:.2f} > 0 & Close {closed_price:.2f} > EMA {closed_ema:.2f} (Closed)"
            
        # In Long Position
        elif self.current_position == 1:
            # 1. Partial Profit Check (uses current high for better fills)
            if self.enable_partial_tp and not self.partial_profit_taken:
                target_price = self.last_entry_price + (atr * self.atr_multiplier)
                # Check if current High hit the target (real-time check)
                if current_high >= target_price:
                    action = "EXIT_LONG_PARTIAL"
                    reason = f"Partial Profit: High {current_high:.2f} >= Target {target_price:.2f} (Entry {self.last_entry_price:.2f} + {self.atr_multiplier}x ATR {atr:.2f})"
            
            # 2. Final Exit Check (uses closed candle)
            # Close < EMA
            if closed_price < closed_ema:
                action = "EXIT_LONG"
                reason = f"Exit Signal (Closed): Close {closed_price:.2f} < EMA {closed_ema:.2f}"
                
        return action, reason

    def update_position_state(self, action: str, current_time_ms: float, indicators: dict = None, price: float = 0.0, reason: str = ""):
        """Update internal state based on executed action."""
        import datetime
        
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')
            
        cci = indicators.get('cci', 0.0) if indicators else 0.0
        
        if action == "ENTRY_LONG":
            self.current_position = 1
            self.last_entry_price = price
            self.partial_profit_taken = False
            
            self.active_trade = {
                "type": "LONG",
                "entry_time": format_time(current_time_ms),
                "entry_price": price,
                "entry_cci": cci,
                "exit_time": None,
                "exit_price": None,
                "exit_cci": None,
                "status": "OPEN",
                "logs": [],
                "partial_exit": False
            }
            
        elif action == "EXIT_LONG_PARTIAL":
            self.partial_profit_taken = True
            if self.active_trade:
                self.active_trade["partial_exit"] = True
                self.active_trade["logs"].append(f"Partial exit at {price:.2f} ({format_time(current_time_ms)})")
                
        elif action == "EXIT_LONG":
            self.current_position = 0
            self.partial_profit_taken = False
            
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["exit_cci"] = cci
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

    def run_backtest(self, df: pd.DataFrame):
        """Simple backtest loop."""
        import ta
        
        self.trades = []
        self.current_position = 0
        self.active_trade = None
        
        if df.empty: return

        # Pre-calc indicators for speed
        cci_series = ta.trend.cci(df['high'], df['low'], df['close'], window=self.cci_length)
        ema_series = ta.trend.ema_indicator(df['close'], window=self.ema_length)
        atr_series = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.atr_length)
        
        for i in range(len(df)):
            if i < self.ema_length: continue
            
            # Create mini-df or just pass values? check_signals expects df for "last" values
            # Efficient way: mock the indicators lookup or adapt check_signals.
            # For simplicity here, we'll manually check logic since we have series.
            
            idx = df.index[i]
            current_time_s = df['time'].iloc[i]
            current_time_ms = current_time_s * 1000
            
            close = df['close'].iloc[i]
            high = df['high'].iloc[i]
            
            cci = cci_series.iloc[i]
            ema = ema_series.iloc[i]
            atr = atr_series.iloc[i]
            
            if pd.isna(cci) or pd.isna(ema): continue
            
            # --- Logic ---
            action = None
            
            if self.current_position == 0:
                # Crossover Check
                # Ensure we have previous value
                prev_cci = cci_series.iloc[i-1]
                
                # Logic: CrossOver 0 AND Close > EMA (at that moment)
                if (prev_cci <= 0) and (cci > 0) and (close > ema):
                    action = "ENTRY_LONG"
                    
            elif self.current_position == 1:
                # Partial
                if self.enable_partial_tp and not self.partial_profit_taken:
                    target = self.last_entry_price + (atr * self.atr_multiplier)
                    if high >= target:
                        action = "EXIT_LONG_PARTIAL"
                
                # Final (Note: Prioritize Final over Partial if both hit in same candle? Or check order?
                # Pine script checks partial first, then final.
                # If Final condition met, we exit all.
                if close < ema:
                    action = "EXIT_LONG"
            
            if action:
                self.update_position_state(action, current_time_ms, {'cci': cci}, close)
                
        logger.info(f"Backtest complete. Trades: {len(self.trades)}")
