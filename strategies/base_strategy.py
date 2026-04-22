import logging
from typing import Dict, Any, Optional
from core.persistence import save_strategy_state, load_strategy_state, clear_strategy_state
from core.config import get_config

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
        
        # New: Shared Indicator State
        self.last_atr: Optional[float] = None

        # Profit Milestones (Global Default or Strategy Override)
        config = get_config()
        # Default global risk settings
        global_rm = getattr(config, 'risk_management', None)
        global_milestones_enabled = global_rm.enable_profit_milestones if global_rm and hasattr(global_rm, 'enable_profit_milestones') else False
        global_milestones = global_rm.profit_milestones if global_rm and hasattr(global_rm, 'profit_milestones') else []
        
        # We will use the strategy-specific override if it exists, otherwise use global default
        cfg = config.settings.get("strategies", {}).get(strategy_name, {})
        self.enable_profit_milestones = cfg.get("enable_profit_milestones", global_milestones_enabled)
        self.profit_milestones = cfg.get("profit_milestones", global_milestones)
        self.milestones_hit = [False] * len(self.profit_milestones)

    def _calculate_atr(self, df, period=14) -> float:
        """
        Standardized ATR (Average True Range) calculation.
        Caches the latest value in self.last_atr and returns it.
        """
        if df.empty or len(df) < period + 1:
            self.last_atr = 0.0
            return 0.0

        import pandas as pd
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        prev_close = df["close"].shift(1).astype(float)
        tr = pd.concat([high - low, abs(high - prev_close), abs(low - prev_close)], axis=1).max(axis=1)
        atr_series = tr.rolling(period).mean()
        
        self.last_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0.0
        return self.last_atr

    def check_profit_milestones(self, current_price: float, live_pos_data: Optional[Dict[str, Any]] = None) -> tuple[Optional[str], str]:
        """
        Check if any profit milestones have been hit.
        Returns: Tuple of (action, reason) or (None, "")
        """
        if not self.enable_profit_milestones or self.current_position == 0:
            return None, ""

        pnl_pct = 0.0
        pnl_source = "Manual"
        
        # Use Exchange Unrealized Margin PnL if available (User Priority)
        if live_pos_data:
            unrealized_pnl = float(live_pos_data.get('unrealized_pnl', 0.0))
            margin = float(live_pos_data.get('margin', 0.0))
            if margin > 0:
                pnl_pct = (unrealized_pnl / margin) * 100.0
                pnl_source = "Exchange"
            else:
                # Fallback to manual if margin is zero
                if self.entry_price:
                    if self.current_position == 1:
                        pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100 * self.leverage
                    else:
                        pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100 * self.leverage
        elif self.entry_price:
            # Manual Fallback (Backtesting or API failure)
            if self.current_position == 1:
                pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100 * self.leverage
            else:
                pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100 * self.leverage

        for idx, milestone in enumerate(self.profit_milestones):
            if self.milestones_hit[idx]:
                continue
            
            # Handle dictionary-based or object-based milestone definitions
            if isinstance(milestone, dict):
                pnl_threshold = milestone.get("pnl_pct", 0.0)
                exit_pct = milestone.get("exit_pct", 0.0)
            else:
                # Fallback if config is loaded as objects
                pnl_threshold = getattr(milestone, "pnl_pct", 0.0)
                exit_pct = getattr(milestone, "exit_pct", 0.0)

            if pnl_pct >= pnl_threshold:
                return "MILESTONE_EXIT", (
                    f"Milestone {idx + 1}: {pnl_source} PnL {pnl_pct:.1f}% >= {pnl_threshold}%"
                    f" | exit_pct={exit_pct}"
                )
        return None, ""

    def handle_milestone_state(self, reason: str, price: float, current_time_ms: float):
        """
        Update state after a MILESTONE_EXIT order executes.
        """
        milestone_idx = 0
        exit_pct = 0.0
        if reason:
            import re
            match = re.search(r"Milestone (\d+):", reason)
            if match:
                milestone_idx = int(match.group(1)) - 1
        
        if 0 <= milestone_idx < len(self.profit_milestones):
            self.milestones_hit[milestone_idx] = True
            
            # Handle dict vs object milestone definition
            milestone = self.profit_milestones[milestone_idx]
            if isinstance(milestone, dict):
                exit_pct = milestone.get("exit_pct", 0.0)
            else:
                exit_pct = getattr(milestone, "exit_pct", 0.0)
            
        if self.active_trade:
            import datetime
            def format_time(ts_ms): 
                return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')

            milestone_trade = self.active_trade.copy()
            milestone_trade["exit_time"] = format_time(current_time_ms)
            milestone_trade["exit_price"] = price
            milestone_trade["status"] = f"MILESTONE_{milestone_idx + 1}"
            milestone_trade["exit_pct"] = exit_pct  # Track exit percentage
            entry = float(self.active_trade.get('entry_price', price))
            milestone_trade["points"] = price - entry if self.current_position == 1 else entry - price
            self.trades.append(milestone_trade)
            self.active_trade["milestone_exit"] = True
            
        self.save_state()

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
                "last_action_candle_ts": self.last_action_candle_ts,
                "milestones_hit": self.milestones_hit
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
            self.milestones_hit = state.get("milestones_hit", [False] * len(self.profit_milestones))
            
            # Return full state so subclass can pull extra fields
            return state
        except Exception as e:
            logger.warning(f"[{self.symbol}] Failed to load state for {self.strategy_name}: {e}")
            return {}

    def reset_milestones(self):
        """Reset the milestone state for a new trade."""
        self.milestones_hit = [False] * len(self.profit_milestones)

    def clear_state(self):
        """Delete the state file from disk and clear cached attributes."""
        self.current_position = 0
        self.entry_price = None
        self.trailing_stop_level = None
        self.last_action_candle_ts = None
        self.reset_milestones()
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

    def reconcile_position(self, size: float, entry_price: float, current_price: float = None, live_pos_data: Optional[Dict] = None) -> tuple[Optional[str], str]:
        raise NotImplementedError("Subclasses must implement reconcile_position")
