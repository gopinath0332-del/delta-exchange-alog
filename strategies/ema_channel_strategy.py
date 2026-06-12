"""
EMA Channel Strategy -- Long & Short (Production Grade)

Pine Script equivalent (ema_channel_strategy.pine):

Upper Band  : EMA(High,  channel_length)  [default 20]
Lower Band  : EMA(Low,   channel_length)  [default 20]
Trend Filter: EMA(Close, trend_length)    [default 200]

Long  Entry : Closed candle > upper band AND close > trend EMA
Long  Exit  : Closed candle < lower band  OR trailing stop hit
Short Entry : Closed candle < lower band AND close < trend EMA
Short Exit  : Closed candle > upper band  OR trailing stop hit

Additional features (parity with DonchianChannelStrategy):
  - ATR trailing stop (ratcheting, per-candle)
  - ATR-based take-profit + PARTIAL_EXIT
  - Fixed stop-loss % with intra-candle SL checks in backtest
  - PnL % exit gate (live exchange data when available)
  - Profit milestone partial exits
  - Custom save_state / _load_from_disk persistence
  - _suppress_persistence guard during backtest
  - _update_bars_per_day hook required by the runner
  - Meaningful exit status labels on trade records
"""

import logging
import datetime
import re
from typing import Dict, Optional, Tuple, Any

import pandas as pd
import numpy as np

from core.config import get_config
from core.candle_utils import get_closed_candle_index
from core.persistence import clear_strategy_state
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


def _fmt(ts_ms: float) -> str:
    return datetime.datetime.fromtimestamp(ts_ms / 1000).strftime("%d-%m-%y %H:%M")


class EMAChannelStrategy(BaseStrategy):
    """
    EMA Channel Strategy -- Both Long and Short (production-grade).

    Channel:
        Upper Band = EMA(High,  channel_length)   [default 20]
        Lower Band = EMA(Low,   channel_length)   [default 20]
    Trend Filter:
        Trend EMA  = EMA(Close, trend_length)     [default 200]

    Exits:
        Primary   : Band breach (close crosses opposite band)
        Secondary : ATR trailing stop (ratchets each candle)
        Optional  : Partial TP at entry +/- (ATR * atr_mult_tp)
        Optional  : Fixed stop-loss % of margin
        Optional  : PnL % exit gate
        Optional  : Profit milestone partial exits
    """

    STRATEGY_NAME = "ema_channel"

    def __init__(self, symbol: str = "BTCUSD"):
        super().__init__(symbol, self.STRATEGY_NAME)

        # -- Config ------------------------------------------------------------
        config = get_config()
        cfg = config.settings.get("strategies", {}).get(self.STRATEGY_NAME, {})

        self.trade_mode     = cfg.get("trade_mode",     "Both")   # Long / Short / Both
        self.channel_length = cfg.get("channel_length",  20)
        self.trend_length   = cfg.get("trend_length",   200)
        self.allow_flip     = cfg.get("allow_flip",      True)

        # ATR-based risk management
        self.atr_period          = cfg.get("atr_period",          14)
        self.atr_mult_tp         = cfg.get("atr_mult_tp",        4.0)
        self.atr_mult_trail      = cfg.get("atr_mult_trail",     2.0)
        self.enable_trailing_stop = cfg.get("enable_trailing_stop", True)  # set False to disable
        self.enable_partial_tp   = cfg.get("enable_partial_tp",  True)
        self.partial_pct         = cfg.get("partial_pct",        0.5)

        # Optional exits
        self.stop_loss_pct = cfg.get("stop_loss_pct", None)   # e.g. 0.50 = 50% of margin
        self.pnl_exit_pct  = cfg.get("pnl_exit_pct",  None)   # e.g. 102 = 102% margin PnL

        # -- Mode Flags --------------------------------------------------------
        self.allow_long  = self.trade_mode in ["Long",  "Both"]
        self.allow_short = self.trade_mode in ["Short", "Both"]

        # -- Strategy-specific persistent state --------------------------------
        self.tp_level          = None   # ATR take-profit price level
        self.partial_exit_done = False  # True after first partial TP fires

        # -- Indicator Cache (live dashboard) ----------------------------------
        self.last_upper_band  = 0.0
        self.last_lower_band  = 0.0
        self.last_trend_ema   = 0.0

        # Closed-candle snapshot (dashboard display)
        self.last_closed_time_str  = "-"
        self.last_closed_upper     = 0.0
        self.last_closed_lower     = 0.0
        self.last_closed_trend_ema = 0.0

        self.indicator_label = "EMACH"

        # -- Restore state from disk (must happen after field defaults) --------
        self.restored_from_disk = self._load_from_disk()

        logger.info(
            f"EMAChannelStrategy initialised: symbol={symbol}, "
            f"channel={self.channel_length}, trend={self.trend_length}, "
            f"trail_mult={self.atr_mult_trail}, tp_mult={self.atr_mult_tp}, "
            f"partial_tp={self.enable_partial_tp}, "
            f"mode={self.trade_mode}, allow_flip={self.allow_flip}"
        )

    # -- Timeframe Hook (REQUIRED by runner -- without this the bot won't start) -

    def _update_bars_per_day(self, timeframe: str):
        """Called by the runner after init to sync bars-per-day to the chosen TF."""
        self.timeframe = timeframe
        tf_to_bars = {
            "1m": 1440, "5m": 288, "15m": 96, "30m": 48,
            "1h": 24, "2h": 12, "3h": 8, "180m": 8,
            "4h": 6, "6h": 4, "12h": 2, "1d": 1,
        }
        self.bars_per_day = tf_to_bars.get(timeframe, 24)
        logger.info(
            f"[{self.symbol}] EMAChannelStrategy: timeframe={timeframe}, "
            f"bars_per_day={self.bars_per_day}"
        )

        # Reset closed-candle display cache on TF change
        self.last_closed_time_str  = "-"
        self.last_closed_upper     = 0.0
        self.last_closed_lower     = 0.0
        self.last_closed_trend_ema = 0.0

    # -- Custom Persistence ----------------------------------------------------

    def save_state(self, extra_data: Optional[Dict[str, Any]] = None):
        """
        Override BaseStrategy.save_state to include EMA-Channel-specific fields
        (tp_level, partial_exit_done, initial_sl_price) so they survive restarts.
        """
        channel_extra = {
            "tp_level":          self.tp_level,
            "partial_exit_done": self.partial_exit_done,
            "initial_sl_price":  self.initial_sl_price,
        }
        if extra_data:
            channel_extra.update(extra_data)
        super().save_state(extra_data=channel_extra)

    def _save_to_disk(self):
        """Save current trade flags to disk (no-op when flat or suppressed)."""
        if self._suppress_persistence:
            return
        if self.current_position == 0:
            self.clear_state()
            return
        self.save_state()

    def _load_from_disk(self) -> bool:
        """
        Restore EMA-Channel-specific flags from disk on cold start.
        Returns True if usable state was found.
        """
        state = self.load_state()
        if not state:
            return False

        self.partial_exit_done = state.get("partial_exit_done", False)
        self.milestones_hit    = state.get("milestones_hit", [False] * len(self.profit_milestones))

        if self.tp_level is None:
            self.tp_level = state.get("tp_level")
        if self.initial_sl_price is None:
            self.initial_sl_price = state.get("initial_sl_price")

        logger.info(
            f"[{self.symbol}] EMAChannelStrategy: state restored from disk -- "
            f"partial_done={self.partial_exit_done}, "
            f"tp_level={self.tp_level}, "
            f"trail_sl={self.trailing_stop_level}, "
            f"initial_sl={self.initial_sl_price}"
        )
        return True

    # -- Helpers ---------------------------------------------------------------

    @staticmethod
    def _ema(series: pd.Series, length: int) -> pd.Series:
        """Standard EMA using pandas ewm -- matches Pine Script ta.ema()."""
        return series.astype(float).ewm(span=length, adjust=False).mean()

    def _compute_bands(self, df: pd.DataFrame):
        """Return (upper_series, lower_series, trend_series) for the full df."""
        upper = self._ema(df["high"],  self.channel_length)
        lower = self._ema(df["low"],   self.channel_length)
        trend = self._ema(df["close"], self.trend_length)
        return upper, lower, trend

    def _compute_atr_series(self, df: pd.DataFrame) -> pd.Series:
        """ATR series using EWM smoothing (same method as Donchian)."""
        high_low   = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close  = np.abs(df["low"]  - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.ewm(span=self.atr_period, adjust=False).mean()

    # -- Interface: calculate_indicators --------------------------------------

    def calculate_indicators(
        self,
        df: pd.DataFrame,
        current_time: Optional[float] = None,
    ) -> Tuple[float, float, float]:
        """
        Calculate EMA Channel bands, 200 EMA trend filter, and ATR.

        Returns:
            (upper_band, lower_band, trend_ema) -- current (live) values.
        """
        min_needed = max(self.channel_length, self.trend_length, self.atr_period) + 1
        if df.empty or len(df) < min_needed:
            return 0.0, 0.0, 0.0

        import time as _time
        if current_time is None:
            current_time = _time.time()

        upper_s, lower_s, trend_s = self._compute_bands(df)

        # Standard ATR for global risk-based sizing (cached in BaseStrategy)
        self._calculate_atr(df, self.atr_period)

        # Live (latest bar) values
        self.last_upper_band = float(upper_s.iloc[-1])
        self.last_lower_band = float(lower_s.iloc[-1])
        self.last_trend_ema  = float(trend_s.iloc[-1])

        # Closed-candle snapshot for dashboard
        closed_idx = get_closed_candle_index(df, current_time * 1000, self.timeframe)
        if len(df) >= abs(closed_idx):
            ts = df["time"].iloc[closed_idx]
            if ts > 1e11:
                ts /= 1000
            self.last_closed_time_str  = datetime.datetime.fromtimestamp(ts).strftime("%H:%M")
            self.last_closed_upper     = float(upper_s.iloc[closed_idx])
            self.last_closed_lower     = float(lower_s.iloc[closed_idx])
            self.last_closed_trend_ema = float(trend_s.iloc[closed_idx])
        else:
            self.last_closed_time_str  = "-"
            self.last_closed_upper     = 0.0
            self.last_closed_lower     = 0.0
            self.last_closed_trend_ema = 0.0

        return self.last_upper_band, self.last_lower_band, self.last_trend_ema

    # -- Interface: check_signals ----------------------------------------------

    def check_signals(
        self,
        df: pd.DataFrame,
        current_time_ms: float,
        live_pos_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], str]:
        """
        Evaluate EMA Channel signals.  Priority order:
          1. Trailing stop hit  (closed-candle check)
          2. PnL % exit gate    (live price)
          3. Partial TP hit     (live price)
          4. Band entry/exit    (closed-candle)
        """
        min_needed = max(self.channel_length, self.trend_length, self.atr_period) + 2
        if df.empty or len(df) < min_needed:
            return None, ""

        current_time_s = current_time_ms / 1000.0
        self.calculate_indicators(df, current_time=current_time_s)

        closed_idx       = get_closed_candle_index(df, current_time_ms, self.timeframe)
        closed_candle_ts = df["time"].iloc[closed_idx]

        # One-action-per-candle guard
        if (
            self.last_action_candle_ts is not None
            and closed_candle_ts <= self.last_action_candle_ts
        ):
            return None, f"Already acted on candle ts={closed_candle_ts}"

        # Values at the closed candle
        upper_s, lower_s, trend_s = self._compute_bands(df)
        atr_s = self._compute_atr_series(df)

        upper      = float(upper_s.iloc[closed_idx])
        lower      = float(lower_s.iloc[closed_idx])
        trend      = float(trend_s.iloc[closed_idx])
        close_c    = float(df["close"].iloc[closed_idx])
        atr_c      = float(atr_s.iloc[closed_idx])

        # Live (latest) price for real-time checks
        current_price = float(df["close"].iloc[-1])

        pos = self.current_position   # 0=flat, 1=long, -1=short

        # -- 1. Update trailing stop (ratchet -- never moves against position) --
        if self.enable_trailing_stop and self.trailing_stop_level is not None:
            if pos == 1:
                new_stop = close_c - (atr_c * self.atr_mult_trail)
                if new_stop > self.trailing_stop_level:
                    self.trailing_stop_level = new_stop
                    logger.debug(
                        f"[{self.symbol}] Trail stop ratcheted UP to {self.trailing_stop_level:.4f}"
                    )
            elif pos == -1:
                new_stop = close_c + (atr_c * self.atr_mult_trail)
                if new_stop < self.trailing_stop_level:
                    self.trailing_stop_level = new_stop
                    logger.debug(
                        f"[{self.symbol}] Trail stop ratcheted DOWN to {self.trailing_stop_level:.4f}"
                    )

        # -- 2. Trailing stop exit (closed-candle) -----------------------------
        if self.enable_trailing_stop and self.trailing_stop_level is not None:
            if pos == 1 and close_c <= self.trailing_stop_level:
                self.last_action_candle_ts = closed_candle_ts
                return "EXIT_LONG", (
                    f"Trailing SL Hit: {close_c:.4f} <= {self.trailing_stop_level:.4f}"
                )
            elif pos == -1 and close_c >= self.trailing_stop_level:
                self.last_action_candle_ts = closed_candle_ts
                return "EXIT_SHORT", (
                    f"Trailing SL Hit: {close_c:.4f} >= {self.trailing_stop_level:.4f}"
                )

        # -- 3. PnL % exit gate (live price, exchange data when available) ------
        if self.pnl_exit_pct is not None and self.entry_price and pos != 0:
            pnl_pct = 0.0
            if live_pos_data:
                unrealized = float(live_pos_data.get("unrealized_pnl", 0.0))
                margin     = float(live_pos_data.get("margin", 0.0))
                if margin > 0:
                    pnl_pct = (unrealized / margin) * 100.0
                else:
                    # Fallback to manual calc when margin field absent
                    if pos == 1:
                        pnl_pct = (current_price - self.entry_price) / self.entry_price * self.leverage * 100
                    else:
                        pnl_pct = (self.entry_price - current_price) / self.entry_price * self.leverage * 100
            else:
                if pos == 1:
                    pnl_pct = (current_price - self.entry_price) / self.entry_price * self.leverage * 100
                else:
                    pnl_pct = (self.entry_price - current_price) / self.entry_price * self.leverage * 100

            if pnl_pct >= self.pnl_exit_pct:
                act = "EXIT_LONG" if pos == 1 else "EXIT_SHORT"
                self.last_action_candle_ts = closed_candle_ts
                return act, f"PnL Exit: {pnl_pct:.1f}% >= {self.pnl_exit_pct}%"

        # -- 4. Partial TP (live price) -----------------------------------------
        if self.enable_partial_tp and not self.partial_exit_done and self.tp_level is not None:
            if pos == 1 and current_price >= self.tp_level:
                return "PARTIAL_EXIT", (
                    f"Partial TP Hit: {current_price:.4f} >= {self.tp_level:.4f}"
                )
            elif pos == -1 and current_price <= self.tp_level:
                return "PARTIAL_EXIT", (
                    f"Partial TP Hit: {current_price:.4f} <= {self.tp_level:.4f}"
                )

        # -- 5. Band entry / exit (closed-candle) ------------------------------

        # FLAT -- check both entry directions
        if pos == 0:
            if self.allow_long and close_c > upper and close_c > trend:
                self.entry_price = close_c
                self.tp_level    = close_c + (atr_c * self.atr_mult_tp)
                self.trailing_stop_level = close_c - (atr_c * self.atr_mult_trail)
                if self.stop_loss_pct is not None:
                    self.initial_sl_price = close_c * (1 - self.stop_loss_pct / self.leverage)
                self.partial_exit_done = False
                self.last_action_candle_ts = closed_candle_ts
                return "ENTRY_LONG", (
                    f"Close ({close_c:.4f}) > Upper ({upper:.4f}) "
                    f"& Close > Trend EMA ({trend:.4f})"
                )

            if self.allow_short and close_c < lower and close_c < trend:
                self.entry_price = close_c
                self.tp_level    = close_c - (atr_c * self.atr_mult_tp)
                self.trailing_stop_level = close_c + (atr_c * self.atr_mult_trail)
                if self.stop_loss_pct is not None:
                    self.initial_sl_price = close_c * (1 + self.stop_loss_pct / self.leverage)
                self.partial_exit_done = False
                self.last_action_candle_ts = closed_candle_ts
                return "ENTRY_SHORT", (
                    f"Close ({close_c:.4f}) < Lower ({lower:.4f}) "
                    f"& Close < Trend EMA ({trend:.4f})"
                )

        # LONG -- check band exit
        elif pos == 1:
            if close_c < lower:
                self.last_action_candle_ts = closed_candle_ts
                return "EXIT_LONG", f"Band Exit: Close ({close_c:.4f}) < Lower ({lower:.4f})"

        # SHORT -- check band exit
        elif pos == -1:
            if close_c > upper:
                self.last_action_candle_ts = closed_candle_ts
                return "EXIT_SHORT", f"Band Exit: Close ({close_c:.4f}) > Upper ({upper:.4f})"

        return None, ""

    # -- Interface: update_position_state -------------------------------------

    def update_position_state(
        self,
        action: str,
        current_time_ms: float,
        indicators: Any = None,
        price: float = 0.0,
        reason: str = "",
    ):
        """Update internal book-keeping after an executed order."""

        ind_str = (
            f"U={self.last_upper_band:.4f} | L={self.last_lower_band:.4f} "
            f"| T={self.last_trend_ema:.4f}"
        )

        # -- Entry Long --------------------------------------------------------
        if action == "ENTRY_LONG":
            self.current_position  = 1
            self.entry_price       = price
            self.partial_exit_done = False
            self.reset_milestones()

            # Set ATR levels if not already set by check_signals (backtest path)
            atr = self.last_atr or 0.0
            if self.tp_level is None:
                self.tp_level = price + (atr * self.atr_mult_tp)
            if self.trailing_stop_level is None:
                self.trailing_stop_level = price - (atr * self.atr_mult_trail)
            if self.stop_loss_pct is not None and self.initial_sl_price is None:
                self.initial_sl_price = price * (1 - self.stop_loss_pct / self.leverage)

            self.active_trade = {
                "type":        "LONG",
                "entry_time":  _fmt(current_time_ms),
                "entry_price": price,
                "entry_bands": ind_str,
                "tp_level":    self.tp_level,
                "trail_sl":    self.trailing_stop_level,
                "status":      "OPEN",
                "logs":        [],
            }

        # -- Entry Short -------------------------------------------------------
        elif action == "ENTRY_SHORT":
            self.current_position  = -1
            self.entry_price       = price
            self.partial_exit_done = False
            self.reset_milestones()

            atr = self.last_atr or 0.0
            if self.tp_level is None:
                self.tp_level = price - (atr * self.atr_mult_tp)
            if self.trailing_stop_level is None:
                self.trailing_stop_level = price + (atr * self.atr_mult_trail)
            if self.stop_loss_pct is not None and self.initial_sl_price is None:
                self.initial_sl_price = price * (1 + self.stop_loss_pct / self.leverage)

            self.active_trade = {
                "type":        "SHORT",
                "entry_time":  _fmt(current_time_ms),
                "entry_price": price,
                "entry_bands": ind_str,
                "tp_level":    self.tp_level,
                "trail_sl":    self.trailing_stop_level,
                "status":      "OPEN",
                "logs":        [],
            }

        # -- Partial Exit ------------------------------------------------------
        elif action == "PARTIAL_EXIT":
            self.partial_exit_done = True
            if self.active_trade:
                partial = self.active_trade.copy()
                entry   = float(self.active_trade.get("entry_price", price))
                partial.update({
                    "exit_time":  _fmt(current_time_ms),
                    "exit_price": price,
                    "status":     "PARTIAL",
                    "exit_pct":   self.partial_pct,
                    "points":     price - entry if self.current_position == 1 else entry - price,
                })
                self.trades.append(partial)
                self.active_trade["partial_exit"] = True

        # -- Milestone Exit ----------------------------------------------------
        elif action == "MILESTONE_EXIT":
            milestone_idx = 0
            exit_pct      = 0.0
            m = re.search(r"Milestone (\d+):", reason)
            if m:
                milestone_idx = int(m.group(1)) - 1

            if 0 <= milestone_idx < len(self.profit_milestones):
                ms = self.profit_milestones[milestone_idx]
                exit_pct = ms.get("exit_pct", 0.0) if isinstance(ms, dict) else getattr(ms, "exit_pct", 0.0)
                self.milestones_hit[milestone_idx] = True

            if self.active_trade:
                ms_trade = self.active_trade.copy()
                entry    = float(self.active_trade.get("entry_price", price))
                ms_trade.update({
                    "exit_time":  _fmt(current_time_ms),
                    "exit_price": price,
                    "status":     f"MILESTONE_{milestone_idx + 1}",
                    "exit_pct":   exit_pct,
                    "points":     price - entry if self.current_position == 1 else entry - price,
                })
                self.trades.append(ms_trade)
                self.active_trade["milestone_exit"] = True

        # -- Exit Long ---------------------------------------------------------
        elif action == "EXIT_LONG":
            self.current_position = 0
            if self.active_trade:
                entry  = float(self.active_trade.get("entry_price", price))
                status = "CLOSED"
                if "Trailing" in reason:
                    status = "TRAIL STOP"
                elif "Band Exit" in reason or "Breakdown" in reason:
                    status = "BAND EXIT"
                elif "PnL Exit" in reason:
                    status = "PNL EXIT"
                elif "Fixed SL" in reason:
                    status = "FIXED SL"
                self.active_trade.update({
                    "exit_time":  _fmt(current_time_ms),
                    "exit_price": price,
                    "exit_bands": ind_str,
                    "status":     status,
                    "points":     price - entry,
                })
                self.trades.append(self.active_trade)
                self.active_trade = None

            self._clear_trade_levels()

        # -- Exit Short --------------------------------------------------------
        elif action == "EXIT_SHORT":
            self.current_position = 0
            if self.active_trade:
                entry  = float(self.active_trade.get("entry_price", price))
                status = "CLOSED"
                if "Trailing" in reason:
                    status = "TRAIL STOP"
                elif "Band Exit" in reason or "Breakout" in reason:
                    status = "BAND EXIT"
                elif "PnL Exit" in reason:
                    status = "PNL EXIT"
                elif "Fixed SL" in reason:
                    status = "FIXED SL"
                self.active_trade.update({
                    "exit_time":  _fmt(current_time_ms),
                    "exit_price": price,
                    "exit_bands": ind_str,
                    "status":     status,
                    "points":     entry - price,
                })
                self.trades.append(self.active_trade)
                self.active_trade = None

            self._clear_trade_levels()

        # Always persist after any state change
        self._save_to_disk()

    def _clear_trade_levels(self):
        """Reset all trade-specific levels after closing a position."""
        self.entry_price       = None
        self.tp_level          = None
        self.trailing_stop_level = None
        self.initial_sl_price  = None
        self.partial_exit_done = False
        self.trade_id          = None
        self.reset_milestones()

    # -- Interface: reconcile_position -----------------------------------------

    def reconcile_position(
        self,
        size: float,
        entry_price: float,
        current_price: float = 0.0,
        live_pos_data: Optional[Dict] = None,
    ) -> Tuple[Optional[str], str]:
        """Sync internal state with exchange position on every live cycle."""
        import time as _time

        def fmt_now() -> str:
            return datetime.datetime.fromtimestamp(_time.time()).strftime("%d-%m-%y %H:%M")

        expected_pos = 0
        if size > 0:
            expected_pos = 1
        elif size < 0:
            expected_pos = -1

        price_changed = (
            self.entry_price is not None
            and abs(self.entry_price - entry_price) > 0.0001
        )

        action = None
        reason = ""

        if self.current_position != expected_pos or price_changed:
            if self.current_position != expected_pos:
                logger.warning(
                    f"[{self.symbol}] Reconcile: internal={self.current_position} "
                    f"-> exchange={expected_pos} (size={size})"
                )
            if price_changed:
                logger.warning(
                    f"[{self.symbol}] Reconcile entry price: "
                    f"internal={self.entry_price} -> exchange={entry_price}"
                )

            # Cold start -- try to restore from disk
            if self.current_position == 0 and expected_pos != 0:
                found = self._load_from_disk()
                if found:
                    logger.info("[reconcile] Cold start: restored from disk state.")
                else:
                    logger.info("[reconcile] Cold start: no persistent state found.")

            # Genuine direction flip -> clear all flags
            truly_new = (self.current_position != 0 and self.current_position != expected_pos)
            old_position = self.current_position

            self.current_position = expected_pos
            self.entry_price      = entry_price

            if truly_new:
                self.reset_milestones()
                self.partial_exit_done = False
                clear_strategy_state(self.symbol, self.STRATEGY_NAME)

            if expected_pos == 0:
                if self.active_trade:
                    action = "EXIT_LONG" if old_position == 1 else "EXIT_SHORT"
                    reason = "External exit (stop-loss or manual)"
                    self.active_trade.update({
                        "exit_time":  f"{fmt_now()} (Rec)",
                        "exit_price": current_price or 0.0,
                        "status":     "CLOSED (SYNC)",
                    })
                    self.trades.append(self.active_trade)
                    self.active_trade = None

                # (flag) Full stale-state cleanup (parity with Donchian)
                self.entry_price         = None
                self.tp_level            = None
                self.trailing_stop_level = None
                self.initial_sl_price    = None
                self.partial_exit_done   = False
                self.trade_id            = None
                self.reset_milestones()
                clear_strategy_state(self.symbol, self.STRATEGY_NAME)

        if expected_pos != 0 and not self.active_trade:
            side = "LONG" if expected_pos == 1 else "SHORT"
            self.active_trade = {
                "type":        side,
                "entry_time":  f"{fmt_now()} (Rec)",
                "entry_price": entry_price,
                "status":      "OPEN",
            }
            self.entry_price = entry_price
            logger.info(
                f"[{self.symbol}] Reconciled -> {side} position "
                f"(size={size}, entry={entry_price})"
            )

        if self.current_position != 0:
            self._save_to_disk()

        return action, reason

    # -- Interface: run_backtest -----------------------------------------------

    def run_backtest(self, df: pd.DataFrame):
        """
        Bar-by-bar backtest that mirrors the full live strategy logic:
          - ATR trailing stop (ratcheting)
          - Intra-candle SL checks using bar high/low
          - ATR partial TP using bar high/low
          - PnL % exit gate
          - Profit milestone partial exits
          - Position flip on same bar

        Disk I/O is suppressed for the entire loop to avoid performance
        degradation and spurious state files.
        """
        logger.info(
            f"EMAChannelStrategy backtest starting: {len(df)} bars [{self.symbol}]"
        )

        # Suppress disk writes for entire backtest run
        prev_suppress = self._suppress_persistence
        self._suppress_persistence = True

        # Reset state
        self.trades             = []
        self.current_position   = 0
        self.active_trade       = None
        self.entry_price        = None
        self.tp_level           = None
        self.trailing_stop_level = None
        self.initial_sl_price   = None
        self.partial_exit_done  = False
        self.reset_milestones()

        if df.empty:
            self._suppress_persistence = prev_suppress
            return

        min_needed = max(self.channel_length, self.trend_length, self.atr_period) + 1

        # Pre-compute all series once
        upper_s, lower_s, trend_s = self._compute_bands(df)
        atr_s = self._compute_atr_series(df)

        for i in range(min_needed, len(df)):
            ts_ms   = float(df["time"].iloc[i]) * 1000
            close   = float(df["close"].iloc[i])
            high    = float(df["high"].iloc[i])
            low     = float(df["low"].iloc[i])

            upper = float(upper_s.iloc[i])
            lower = float(lower_s.iloc[i])
            trend = float(trend_s.iloc[i])
            atr   = float(atr_s.iloc[i])

            if any(pd.isna(v) for v in (upper, lower, trend, atr)):
                continue

            # Update live indicator cache (for state snapshots in active_trade)
            self.last_upper_band = upper
            self.last_lower_band = lower
            self.last_trend_ema  = trend
            self.last_atr        = atr

            indicators = {"upper_band": upper, "lower_band": lower, "trend_ema": trend}
            pos = self.current_position

            # -- 1. Update trailing stop (ratchet) -----------------------------
            if self.enable_trailing_stop and self.trailing_stop_level is not None:
                if pos == 1:
                    new_stop = close - (atr * self.atr_mult_trail)
                    if new_stop > self.trailing_stop_level:
                        self.trailing_stop_level = new_stop
                elif pos == -1:
                    new_stop = close + (atr * self.atr_mult_trail)
                    if new_stop < self.trailing_stop_level:
                        self.trailing_stop_level = new_stop

            # -- 2. PnL % exit (using close price as approximation) ------------
            if self.pnl_exit_pct is not None and self.entry_price and pos != 0:
                if pos == 1:
                    pnl_pct = (close - self.entry_price) / self.entry_price * self.leverage * 100
                else:
                    pnl_pct = (self.entry_price - close) / self.entry_price * self.leverage * 100
                if pnl_pct >= self.pnl_exit_pct:
                    act = "EXIT_LONG" if pos == 1 else "EXIT_SHORT"
                    rsn = f"PnL Exit: {pnl_pct:.1f}% >= {self.pnl_exit_pct}%"
                    self.update_position_state(act, ts_ms, indicators, close, rsn)
                    continue

            # -- 3. Fixed SL hit (intra-candle using bar low/high) -------------
            if self.initial_sl_price is not None:
                if pos == 1 and low <= self.initial_sl_price:
                    self.update_position_state(
                        "EXIT_LONG", ts_ms, indicators, self.initial_sl_price, "Fixed SL Hit"
                    )
                    continue
                elif pos == -1 and high >= self.initial_sl_price:
                    self.update_position_state(
                        "EXIT_SHORT", ts_ms, indicators, self.initial_sl_price, "Fixed SL Hit"
                    )
                    continue

            # -- 4. Trailing SL hit (intra-candle using bar low/high) ----------
            if self.enable_trailing_stop and self.trailing_stop_level is not None:
                if pos == 1 and low <= self.trailing_stop_level:
                    self.update_position_state(
                        "EXIT_LONG", ts_ms, indicators, self.trailing_stop_level, "Trailing SL Hit"
                    )
                    continue
                elif pos == -1 and high >= self.trailing_stop_level:
                    self.update_position_state(
                        "EXIT_SHORT", ts_ms, indicators, self.trailing_stop_level, "Trailing SL Hit"
                    )
                    continue

            # -- 5. Partial TP (intra-candle using bar high/low) ---------------
            if self.enable_partial_tp and not self.partial_exit_done and self.tp_level is not None:
                if pos == 1 and high >= self.tp_level:
                    self.update_position_state(
                        "PARTIAL_EXIT", ts_ms, indicators, self.tp_level,
                        f"Partial TP Hit: {self.tp_level:.4f}"
                    )
                elif pos == -1 and low <= self.tp_level:
                    self.update_position_state(
                        "PARTIAL_EXIT", ts_ms, indicators, self.tp_level,
                        f"Partial TP Hit: {self.tp_level:.4f}"
                    )

            # -- 6. Profit milestones (intra-candle using bar high/low) ---------
            if self.enable_profit_milestones and self.entry_price and pos != 0:
                for idx, milestone in enumerate(self.profit_milestones):
                    if self.milestones_hit[idx]:
                        continue
                    pnl_threshold = milestone["pnl_pct"] if isinstance(milestone, dict) else milestone.pnl_pct
                    exit_pct      = milestone["exit_pct"] if isinstance(milestone, dict) else milestone.exit_pct
                    if pos == 1:
                        ms_price = self.entry_price * (1 + pnl_threshold / (100 * self.leverage))
                        if high >= ms_price:
                            rsn = f"Milestone {idx+1}: PnL >= {pnl_threshold}% | exit_pct={exit_pct}"
                            self.update_position_state("MILESTONE_EXIT", ts_ms, indicators, ms_price, rsn)
                            break
                    else:
                        ms_price = self.entry_price * (1 - pnl_threshold / (100 * self.leverage))
                        if low <= ms_price:
                            rsn = f"Milestone {idx+1}: PnL >= {pnl_threshold}% | exit_pct={exit_pct}"
                            self.update_position_state("MILESTONE_EXIT", ts_ms, indicators, ms_price, rsn)
                            break

            # Re-read position after any early exit above
            pos = self.current_position

            # -- 7. Band channel entries & exits ------------------------------
            if pos == 0:
                if self.allow_long and close > upper and close > trend:
                    self.tp_level            = close + (atr * self.atr_mult_tp)
                    self.trailing_stop_level = close - (atr * self.atr_mult_trail)
                    if self.stop_loss_pct is not None:
                        self.initial_sl_price = close * (1 - self.stop_loss_pct / self.leverage)
                    self.update_position_state(
                        "ENTRY_LONG", ts_ms, indicators, close, "Band Entry Long"
                    )
                elif self.allow_short and close < lower and close < trend:
                    self.tp_level            = close - (atr * self.atr_mult_tp)
                    self.trailing_stop_level = close + (atr * self.atr_mult_trail)
                    if self.stop_loss_pct is not None:
                        self.initial_sl_price = close * (1 + self.stop_loss_pct / self.leverage)
                    self.update_position_state(
                        "ENTRY_SHORT", ts_ms, indicators, close, "Band Entry Short"
                    )

            elif pos == 1:
                if close < lower:
                    self.update_position_state(
                        "EXIT_LONG", ts_ms, indicators, close, "Band Exit Long"
                    )
                    # Flip to short if conditions met
                    if self.allow_flip and self.allow_short and close < trend:
                        self.tp_level            = close - (atr * self.atr_mult_tp)
                        self.trailing_stop_level = close + (atr * self.atr_mult_trail)
                        if self.stop_loss_pct is not None:
                            self.initial_sl_price = close * (1 + self.stop_loss_pct / self.leverage)
                        self.update_position_state(
                            "ENTRY_SHORT", ts_ms, indicators, close, "Flip to Short"
                        )

            elif pos == -1:
                if close > upper:
                    self.update_position_state(
                        "EXIT_SHORT", ts_ms, indicators, close, "Band Exit Short"
                    )
                    # Flip to long if conditions met
                    if self.allow_flip and self.allow_long and close > trend:
                        self.tp_level            = close + (atr * self.atr_mult_tp)
                        self.trailing_stop_level = close - (atr * self.atr_mult_trail)
                        if self.stop_loss_pct is not None:
                            self.initial_sl_price = close * (1 - self.stop_loss_pct / self.leverage)
                        self.update_position_state(
                            "ENTRY_LONG", ts_ms, indicators, close, "Flip to Long"
                        )

        self._suppress_persistence = prev_suppress
        logger.info(
            f"EMAChannelStrategy backtest complete: "
            f"{len(self.trades)} trades, "
            f"final position={self.current_position} [{self.symbol}]"
        )
