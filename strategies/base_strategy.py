import logging
from typing import Dict, Any, Optional
from core.persistence import save_strategy_state, load_strategy_state, clear_strategy_state

logger = logging.getLogger(__name__)

class BaseStrategy:
    """
    Base class for all trading strategies in the Delta Exchange bot.
    Provides standardized state persistence (saving/loading trade state).
    """

    def __init__(self, symbol: str, strategy_name: str):
        self.symbol = symbol
        self.strategy_name = strategy_name
        
        # Standard Trading State (Persisted)
        self.current_position = 0  # 1=LONG, -1=SHORT, 0=FLAT
        self.entry_price: Optional[float] = None
        self.trailing_stop_level: Optional[float] = None
        self.last_action_candle_ts: Optional[float] = None
        
        # Standard metadata (Cached/Live only)
        self.active_trade: Optional[Dict[str, Any]] = None
        self.trades: list = []
        self.timeframe: str = "1h"
        self.indicator_label: str = "IND"
        self.leverage: int = 1

    def save_state(self, extra_data: Optional[Dict[str, Any]] = None):
        """
        Save the current strategy state to disk.
        Args:
            extra_data: Optional dict of strategy-specific fields to persist.
        """
        try:
            state = {
                "current_position": self.current_position,
                "entry_price": self.entry_price,
                "trailing_stop_level": self.trailing_stop_level,
                "last_action_candle_ts": self.last_action_candle_ts
            }
            
            if extra_data:
                state.update(extra_data)
                
            save_strategy_state(self.symbol, self.strategy_name, state)
        except Exception as e:
            logger.error(f"[{self.symbol}] Failed to save state for {self.strategy_name}: {e}")

    def load_state(self) -> Dict[str, Any]:
        """
        Load strategy state from disk and restore common attributes.
        Returns:
            Dict of "extra" data that the subclass might need to process.
        """
        try:
            state = load_strategy_state(self.symbol, self.strategy_name)
            if not state:
                return {}

            # Restore standard attributes
            self.current_position = state.get("current_position", 0)
            self.entry_price = state.get("entry_price")
            self.trailing_stop_level = state.get("trailing_stop_level")
            self.last_action_candle_ts = state.get("last_action_candle_ts")
            
            # Return full state so subclass can pull extra fields
            return state
        except Exception as e:
            logger.warning(f"[{self.symbol}] Failed to load state for {self.strategy_name}: {e}")
            return {}

    def clear_state(self):
        """Delete the state file from disk."""
        clear_strategy_state(self.symbol, self.strategy_name)

    # ─────────────────────────────────────────────────────────────────────────
    # Interface hooks (to be overridden by subclasses)
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_indicators(self, df, current_time=None):
        raise NotImplementedError("Subclasses must implement calculate_indicators")

    def check_signals(self, df, current_time_ms, live_pos_data=None):
        raise NotImplementedError("Subclasses must implement check_signals")

    def update_position_state(self, action, current_time_ms, indicators=None, price=0.0, reason=""):
        raise NotImplementedError("Subclasses must implement update_position_state")

    def run_backtest(self, df):
        raise NotImplementedError("Subclasses must implement run_backtest")

    def reconcile_position(self, size, entry_price, current_price=None, live_pos_data=None):
        raise NotImplementedError("Subclasses must implement reconcile_position")
