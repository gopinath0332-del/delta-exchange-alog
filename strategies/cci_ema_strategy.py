import logging
from typing import Dict, Optional, Tuple, Any

import pandas as pd
import ta

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
    - ATR Length: 14
    - ATR Multiplier: 4.0
    """
    
    def __init__(self):
        # Parameters
        self.cci_length = 30
        self.ema_length = 50
        self.atr_length = 14
        self.atr_multiplier = 4.0
        
        self.indicator_label = "CCI"
        
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
        Check for entry/exit signals.
        """
        if df.empty:
            return None, ""
            
        # Get indicators
        cci, ema, atr = self.calculate_indicators(df)
        close = df['close'].iloc[-1]
        high = df['high'].iloc[-1] # For partial exit check
        
        action = None
        reason = ""
        
        # --- Logic ---
        
        # Trend Filter: Close > EMA
        trend_bullish = close > ema
        
        # Entry Long
        # Condition: CCI CrossOver 0 AND Trend Bullish
        # Note: We check if CCI > 0 and we are not in position. 
        # Ideally check crossover, but absolute level > 0 is fine if we check state.
        if self.current_position == 0:
            # Requires previous CCI for crossover check
            prev_cci = self.calculate_prev_cci(df) # Need to implement this helper or fetch directly
            if prev_cci is not None:
                # Crossover: Prev <= 0 AND Curr > 0
                cci_cross = (prev_cci <= 0) and (cci > 0)
                if cci_cross and trend_bullish:
                    action = "ENTRY_LONG"
                    reason = f"CCI Cross {prev_cci:.2f}->{cci:.2f} > 0 & Close {close:.2f} > EMA {ema:.2f}"
                
        # In Long Position
        elif self.current_position == 1:
            # 1. Partial Profit Check
            if not self.partial_profit_taken:
                target_price = self.last_entry_price + (atr * self.atr_multiplier)
                # Check if High hit the target
                if high >= target_price:
                    action = "EXIT_LONG_PARTIAL"
                    reason = f"Partial Profit: High {high:.2f} >= Target {target_price:.2f} (Entry {self.last_entry_price:.2f} + {self.atr_multiplier}x ATR {atr:.2f})"
            
            # 2. Final Exit Check
            # CCI CrossUnder 0 OR Close < EMA
            if close < ema:
                action = "EXIT_LONG"
                reason = f"Exit Signal: Close {close:.2f} < EMA {ema:.2f}"
                
        return action, reason

    def update_position_state(self, action: str, current_time_ms: float, indicators: dict = None, price: float = 0.0):
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
                "status": "OPEN",
                "logs": []
            }
            
        elif action == "EXIT_LONG_PARTIAL":
            self.partial_profit_taken = True
            if self.active_trade:
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
                if not self.partial_profit_taken:
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
