import logging
from typing import Dict, Optional, Tuple, Any
import pandas as pd
import ta
import numpy as np
from core.config import get_config

logger = logging.getLogger(__name__)

class MACDPSAR100EMAStrategy:
    """
    MACD + 100 EMA + PSAR Filtered Long Only Strategy.
    
    Logic:
    - Long Entry: Close > EMA100 AND MACD Hist > 0 AND Price > PSAR
    - Long Exit: Price < PSAR
    """
    
    def __init__(self):
        # Load Config
        config = get_config()
        cfg = config.settings.get("strategies", {}).get("macd_psar_100ema", {})

        # Parameters
        self.macd_fast = cfg.get("macd_fast", 14)
        self.macd_slow = cfg.get("macd_slow", 26)
        self.macd_signal = cfg.get("macd_signal", 9)
        self.ema_length = cfg.get("ema_length", 100)
        self.sar_start = cfg.get("sar_start", 0.005)
        self.sar_increment = cfg.get("sar_increment", 0.005)
        self.sar_max = cfg.get("sar_max", 0.2)
        
        # Dashboard/Live State
        self.last_macd_line = 0.0
        self.last_signal_line = 0.0
        self.last_hist = 0.0
        self.last_ema = 0.0
        self.last_sar = 0.0
        
        self.current_position = 0  # 1 for Long, 0 for Flat
        self.indicator_label = "Hist" # Dashboard Label
        
        # Trade History
        self.trades = [] 
        self.active_trade = None
        
    def calculate_indicators(self, df: pd.DataFrame):
        """Calculate Technical Indicators (MACD, EMA, SAR)."""
        if len(df) < max(self.macd_slow, self.ema_length) + 1:
            return df
        
        df = df.copy()

        # MACD
        macd = ta.trend.MACD(
            close=df['close'], 
            window_slow=self.macd_slow, 
            window_fast=self.macd_fast, 
            window_sign=self.macd_signal
        )
        df['macd_line'] = macd.macd()
        df['signal_line'] = macd.macd_signal()
        df['macd_hist'] = macd.macd_diff()
        
        # EMA
        ema = ta.trend.EMAIndicator(close=df['close'], window=self.ema_length)
        df['ema'] = ema.ema_indicator()
        
        # PSAR
        # ta library PSARIndicator uses step and max_step.
        # It doesn't seemingly support 'start' but in most implementations step = start initially.
        psar = ta.trend.PSARIndicator(
            high=df['high'], 
            low=df['low'], 
            close=df['close'], 
            step=self.sar_increment, 
            max_step=self.sar_max
        )
        df['sar'] = psar.psar()
        
        return df

    def check_signals(self, df: pd.DataFrame, current_time_ms: float) -> Tuple[str, str]:
        """Check for entry/exit signals."""
        
        # 1. Update Indicators
        df = self.calculate_indicators(df)
        
        if len(df) < 5 or 'sar' not in df.columns:
            return None, ""
            
        current_candle = df.iloc[-1]
        
        try:
            current_close = float(current_candle['close'])
            current_ema = float(current_candle['ema'])
            current_sar = float(current_candle['sar'])
            current_hist = float(current_candle['macd_hist'])
            
            # Update State
            self.last_ema = current_ema
            self.last_sar = current_sar
            self.last_hist = current_hist
            self.last_macd_line = float(current_candle['macd_line'])
            self.last_signal_line = float(current_candle['signal_line'])
            
        except (KeyError, ValueError, TypeError):
             return None, ""
             
        action = None
        reason = ""
        
        # --- LOGIC ---
        
        # Long Entry: Close > EMA + Hist > 0 + Close > SAR
        long_condition = (current_close > current_ema) and (current_hist > 0) and (current_close > current_sar)
        
        # Exit: Close < SAR
        exit_condition = (current_close < current_sar)
        
        if self.current_position == 1: # Already Long
            if exit_condition:
                action = "EXIT_LONG"
                reason = f"Close ({current_close:.2f}) < SAR ({current_sar:.2f})"
                return action, reason
                
        elif self.current_position == 0: # Flat
            if long_condition:
                action = "ENTRY_LONG"
                parts = []
                if current_close > current_ema: parts.append(f"Close > EMA({current_ema:.2f})")
                if current_hist > 0: parts.append(f"Hist({current_hist:.2f}) > 0")
                if current_close > current_sar: parts.append(f"Close > SAR({current_sar:.2f})")
                
                reason = " & ".join(parts)
                return action, reason
                
        return None, ""

    def update_position_state(self, action: str, current_time_ms: float, current_rsi: float = 0.0, price: float = 0.0, reason: str = ""):
        """Update internal state."""
        import datetime
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')
            
        if action == "ENTRY_LONG":
            self.current_position = 1
            self.active_trade = {
                "type": "LONG",
                "entry_time": format_time(current_time_ms),
                "entry_price": price,
                "entry_hist": self.last_hist, # Log MACD Hist for Dashboard
                "entry_macd_hist": self.last_hist, # Keep for legacy/debug
                "entry_ema": self.last_ema,
                "exit_time": "-",
                "exit_price": "-",
                "status": "OPEN",
                "points": None
            }
            
        elif action == "EXIT_LONG":
            self.current_position = 0
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["exit_hist"] = self.last_hist # Log Exit Hist
                self.active_trade["status"] = "CLOSED"
                self.active_trade["points"] = price - float(self.active_trade['entry_price'])
                self.trades.append(self.active_trade)
                self.active_trade = None

    def reconcile_position(self, size: float, entry_price: float):
        """Reconcile state."""
        import time
        import datetime
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')

        current_ts = int(time.time() * 1000)
        expected_pos = 1 if size > 0 else 0
        
        if self.current_position != expected_pos:
            logger.warning(f"Reconciling: Internal {self.current_position} -> Exchange {expected_pos}")
            self.current_position = expected_pos
            
            if expected_pos == 1 and not self.active_trade:
                self.active_trade = {
                    "type": "LONG",
                    "entry_time": format_time(current_ts) + " (Rec)",
                    "entry_price": entry_price,
                    "status": "OPEN",
                    "points": None
                }
            elif expected_pos == 0 and self.active_trade:
                self.active_trade["exit_time"] = format_time(current_ts) + " (Rec)"
                self.active_trade["status"] = "CLOSED"
                self.trades.append(self.active_trade)
                self.active_trade = None
                
    def run_backtest(self, df: pd.DataFrame):
        """Run backtest."""
        self.trades = []
        self.active_trade = None
        self.current_position = 0
        
        if df.empty: return
        
        # Indicators
        df = self.calculate_indicators(df)
        
        start_idx = max(self.macd_slow, self.ema_length) + 1
        for i in range(start_idx, len(df)):
            subset = df.iloc[:i+1]
            current_time = float(df['time'].iloc[i]) * 1000
            current_price = float(df['close'].iloc[i])
            
            action, reason = self.check_signals(subset, current_time)
            
            if action:
                self.update_position_state(action, current_time, price=current_price, reason=reason)
                
        logger.info(f"Backtest complete. Trades: {len(self.trades)}")
