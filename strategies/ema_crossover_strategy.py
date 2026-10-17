"""
EMA Crossover Strategy for CrudeOil (CRUDEOILUSD)

Strategy Logic (from pine/ema-cross-over.pin):
- Fast EMA (default: 20) and Slow EMA (default: 50) crossover signals.
- 200 EMA trend filter: Only long above EMA(200), only short below EMA(200).
- ADX choppiness filter: Skip entries when ADX < threshold.
- Breakout mode: Enter when price / fast EMA crosses the 200 EMA while
  the fast/slow EMA pair is already crossed in the right direction.
- Allow Flip: Close & reverse on the same bar.

Donchian-style Risk Management (ported from donchian_strategy.py):
- ATR trailing stop (ratchets each candle, never moves against the trade).
- ATR-based partial take-profit (fires as soon as price touches the level).
- Profit Milestone Exit (configured globally or per-strategy in settings.yaml).
- Fixed stop-loss % of margin (optional hard floor).
- PnL% exit gate (optional — close when unrealised margin PnL reaches target).
"""

import logging
import datetime
import re
from typing import Dict, Optional, Tuple, Any

import numpy as np
import pandas as pd

from core.config import get_config
from core.candle_utils import get_closed_candle_index
from core.persistence import clear_strategy_state
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


def _fmt(ts_ms: float) -> str:
    return datetime.datetime.fromtimestamp(ts_ms / 1000).strftime("%d-%m-%y %H:%M")


class EMACrossoverStrategy(BaseStrategy):
    """
    EMA Crossover Strategy for CrudeOil.

    Signals:
      - Long  entry: fast EMA crosses above slow EMA (+ optional 200 EMA / ADX filters)
      - Short entry: fast EMA crosses below slow EMA (+ optional 200 EMA / ADX filters)
      - Breakout long/short: price or fast EMA crosses the 200 EMA while EMAs are
        already aligned, enabling re-entry after a trend-resumption.

    Risk management (Donchian-style):
      - ATR trailing stop (ratchets each bar)
      - ATR partial take-profit
      - Profit milestone exit (global or per-strategy config)
      - Hard fixed SL % of margin
      - PnL % exit gate
    """

    STRATEGY_KEY = "ema_crossover"

    def __init__(self, symbol: str = "CRUDEOILUSD"):
        super().__init__(symbol, self.STRATEGY_KEY)

        config = get_config()
        cfg: Dict = config.settings.get("strategies", {}).get(self.STRATEGY_KEY, {})

        # ── EMA Parameters ─────────────────────────────────────────────────────
        self.trade_mode: str = cfg.get("trade_mode", "Both")  # "Long", "Short", "Both"
        self.fast_len: int = cfg.get("fast_len", 20)
        self.slow_len: int = cfg.get("slow_len", 50)

        # ── 200 EMA Trend Filter ───────────────────────────────────────────────
        self.use_trend_filter: bool = cfg.get("use_trend_filter", True)
        self.trend_len: int = cfg.get("trend_len", 200)
        self.allow_breakout: bool = cfg.get("allow_breakout", True)

        # ── ADX Choppiness Filter ──────────────────────────────────────────────
        self.use_adx_filter: bool = cfg.get("use_adx_filter", True)
        self.adx_len: int = cfg.get("adx_len", 15)
        self.adx_thresh: float = cfg.get("adx_thresh", 20.0)

        # ── General Settings ───────────────────────────────────────────────────
        self.allow_flip: bool = cfg.get("allow_flip", True)

        # ── ATR / Risk Management ──────────────────────────────────────────────
        self.atr_period: int = cfg.get("atr_period", 14)
        self.atr_mult_tp: float = cfg.get("atr_mult_tp", 4.0)
        self.atr_mult_trail: float = cfg.get("atr_mult_trail", 2.0)
        self.enable_partial_tp: bool = cfg.get("enable_partial_tp", True)
        self.partial_pct: float = cfg.get("partial_pct", 0.5)
        self.stop_loss_pct: Optional[float] = cfg.get("stop_loss_pct", None)
        self.pnl_exit_pct: Optional[float] = cfg.get("pnl_exit_pct", None)

        # ── Direction Flags ────────────────────────────────────────────────────
        self.allow_long: bool = self.trade_mode in ["Long", "Both"]
        self.allow_short: bool = self.trade_mode in ["Short", "Both"]

        # ── Dashboard / Labels ─────────────────────────────────────────────────
        self.indicator_label = "EMA-X"
        self.timeframe = "1h"

        # ── Per-trade State ────────────────────────────────────────────────────
        self.tp_level: Optional[float] = None
        self.partial_exit_done: bool = False

        # ── Indicator Cache (dashboard) ────────────────────────────────────────
        self.last_fast_ema: float = 0.0
        self.last_slow_ema: float = 0.0
        self.last_trend_ema: float = 0.0
        self.last_adx: float = 0.0

        # Closed candle cache
        self.last_closed_time_str: str = "-"

        # ── Restore from disk ──────────────────────────────────────────────────
        self._load_from_disk()

        logger.info(
            f"EMACrossoverStrategy initialised: symbol={symbol}, "
            f"mode={self.trade_mode}, fast={self.fast_len}, slow={self.slow_len}, "
            f"trend={self.trend_len}, ADX={self.use_adx_filter}(>{self.adx_thresh}), "
            f"flip={self.allow_flip}, ATR_TP={self.atr_mult_tp}x, "
            f"ATR_Trail={self.atr_mult_trail}x, partial={self.enable_partial_tp}"
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Indicator Calculation
    # ══════════════════════════════════════════════════════════════════════════

    def _calc_adx(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Compute ADX using Wilder smoothing (matches Pine ta.dmi())."""
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)

        up_move = high.diff()
        down_move = -low.diff()

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        tr = pd.concat(
            [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
            axis=1,
        ).max(axis=1)

        # Wilder smoothing (RMA / EWM with alpha=1/period)
        alpha = 1.0 / period
        atr_w = tr.ewm(alpha=alpha, adjust=False).mean()
        plus_di = (
            pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean()
            / atr_w
            * 100
        )
        minus_di = (
            pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean()
            / atr_w
            * 100
        )

        dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
        adx = dx.ewm(alpha=alpha, adjust=False).mean()
        return adx

    def calculate_indicators(
        self, df: pd.DataFrame, current_time: Optional[float] = None
    ) -> Tuple[float, float, float, float]:
        """
        Calculate Fast EMA, Slow EMA, Trend EMA (200), ATR and ADX.

        Returns:
            (fast_ema, slow_ema, trend_ema, adx_val)
        """
        min_len = max(self.fast_len, self.slow_len, self.trend_len, self.adx_len) + 1
        if len(df) < min_len:
            return 0.0, 0.0, 0.0, 0.0

        if current_time is None:
            import time
            current_time = time.time()

        close = df["close"].astype(float)
        fast_s = close.ewm(span=self.fast_len, adjust=False).mean()
        slow_s = close.ewm(span=self.slow_len, adjust=False).mean()
        trend_s = close.ewm(span=self.trend_len, adjust=False).mean()
        adx_s = self._calc_adx(df, self.adx_len)

        # Cache ATR for position sizing
        self._calculate_atr(df, self.atr_period)

        self.last_fast_ema = float(fast_s.iloc[-1])
        self.last_slow_ema = float(slow_s.iloc[-1])
        self.last_trend_ema = float(trend_s.iloc[-1])
        self.last_adx = float(adx_s.iloc[-1])

        # Closed-candle cache
        try:
            closed_idx = get_closed_candle_index(df, current_time * 1000, self.timeframe)
            ts = df["time"].iloc[closed_idx]
            if ts > 1e11:
                ts /= 1000
            self.last_closed_time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M")
        except Exception:
            self.last_closed_time_str = "-"

        return self.last_fast_ema, self.last_slow_ema, self.last_trend_ema, self.last_adx

    # ══════════════════════════════════════════════════════════════════════════
    # Signal Engine
    # ══════════════════════════════════════════════════════════════════════════

    def check_signals(
        self,
        df: pd.DataFrame,
        current_time_ms: float,
        live_pos_data: Optional[Dict] = None,
    ) -> Tuple[Optional[str], str]:
        """
        Evaluate trading signals on the last **closed** candle.

        Priority order (same as Donchian):
          1. ATR Trailing Stop
          2. Fixed Hard Stop-Loss (intra-bar)
          3. PnL % exit gate (live price)
          4. ATR Partial Take-Profit (live price)
          5. Profit Milestone Exit (live price)
          6. EMA Crossover / Breakout entries & opposite-cross exits
        """
        min_len = max(self.fast_len, self.slow_len, self.trend_len, self.adx_len) + 2
        if df.empty or len(df) < min_len:
            return None, ""

        current_time_s = current_time_ms / 1000.0
        self.calculate_indicators(df, current_time=current_time_s)

        closed_idx = get_closed_candle_index(df, current_time_ms, self.timeframe)
        closed_candle_ts = df["time"].iloc[closed_idx]

        # One-action-per-candle guard
        if (
            self.last_action_candle_ts is not None
            and closed_candle_ts <= self.last_action_candle_ts
        ):
            return None, f"One-action rule: candle {closed_candle_ts} already acted on"

        prev_idx = closed_idx - 1

        # Pre-calculate all indicator series at closed index
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        fast_s = close.ewm(span=self.fast_len, adjust=False).mean()
        slow_s = close.ewm(span=self.slow_len, adjust=False).mean()
        trend_s = close.ewm(span=self.trend_len, adjust=False).mean()
        adx_s = self._calc_adx(df, self.adx_len)

        # ATR at closed index
        tr = pd.concat(
            [
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr_s = tr.ewm(span=self.atr_period, adjust=False).mean()

        close_c = float(close.iloc[closed_idx])
        fast_c = float(fast_s.iloc[closed_idx])
        slow_c = float(slow_s.iloc[closed_idx])
        trend_c = float(trend_s.iloc[closed_idx])
        adx_c = float(adx_s.iloc[closed_idx])
        atr_c = float(atr_s.iloc[closed_idx])

        fast_p = float(fast_s.iloc[prev_idx])
        slow_p = float(slow_s.iloc[prev_idx])
        trend_p = float(trend_s.iloc[prev_idx])

        current_price = float(close.iloc[-1])
        current_low = float(low.iloc[-1])
        current_high = float(high.iloc[-1])

        # ── 1. ATR Trailing Stop Update ────────────────────────────────────────
        if self.trailing_stop_level is not None:
            if self.current_position == 1:
                new_stop = close_c - (atr_c * self.atr_mult_trail)
                if new_stop > self.trailing_stop_level:
                    self.trailing_stop_level = new_stop
            elif self.current_position == -1:
                new_stop = close_c + (atr_c * self.atr_mult_trail)
                if new_stop < self.trailing_stop_level:
                    self.trailing_stop_level = new_stop

        # ── 2. ATR Trailing Stop Hit ───────────────────────────────────────────
        if self.trailing_stop_level is not None:
            if self.current_position == 1 and close_c <= self.trailing_stop_level:
                self.last_action_candle_ts = closed_candle_ts
                return "EXIT_LONG", (
                    f"Trailing SL Hit: {close_c:.4f} <= {self.trailing_stop_level:.4f}"
                )
            elif self.current_position == -1 and close_c >= self.trailing_stop_level:
                self.last_action_candle_ts = closed_candle_ts
                return "EXIT_SHORT", (
                    f"Trailing SL Hit: {close_c:.4f} >= {self.trailing_stop_level:.4f}"
                )

        # ── 3. PnL % Exit Gate (live price) ───────────────────────────────────
        if self.pnl_exit_pct is not None and self.entry_price and self.current_position != 0:
            unrealized_pnl_pct = 0.0
            if live_pos_data:
                unrealized_pnl = float(live_pos_data.get("unrealized_pnl", 0.0))
                margin = float(live_pos_data.get("margin", 0.0))
                if margin > 0:
                    unrealized_pnl_pct = (unrealized_pnl / margin) * 100.0
                else:
                    unrealized_pnl_pct = self._manual_pnl(current_price)
            else:
                unrealized_pnl_pct = self._manual_pnl(current_price)

            if unrealized_pnl_pct >= self.pnl_exit_pct:
                action_str = "EXIT_LONG" if self.current_position == 1 else "EXIT_SHORT"
                reason_str = f"PnL Exit: {unrealized_pnl_pct:.1f}% >= {self.pnl_exit_pct}%"
                self.last_action_candle_ts = closed_candle_ts
                return action_str, reason_str

        # ── 4. ATR Partial Take-Profit (live price) ────────────────────────────
        if (
            self.enable_partial_tp
            and not self.partial_exit_done
            and self.tp_level is not None
        ):
            if self.current_position == 1 and current_price >= self.tp_level:
                return "PARTIAL_EXIT", (
                    f"Partial TP Hit: {current_price:.4f} >= {self.tp_level:.4f}"
                )
            elif self.current_position == -1 and current_price <= self.tp_level:
                return "PARTIAL_EXIT", (
                    f"Partial TP Hit: {current_price:.4f} <= {self.tp_level:.4f}"
                )

        # ── 5. Profit Milestone Exit (live price) ──────────────────────────────
        milestone_action, milestone_reason = self.check_profit_milestones(
            current_price, live_pos_data
        )
        if milestone_action:
            return milestone_action, milestone_reason

        # ── 6. EMA Signal Logic ────────────────────────────────────────────────
        # Detect raw crossovers on closed candle vs. previous candle
        raw_long_cross = (fast_p <= slow_p) and (fast_c > slow_c)   # fast crosses above slow
        raw_short_cross = (fast_p >= slow_p) and (fast_c < slow_c)   # fast crosses below slow

        # Trend filter conditions
        trend_long_ok = (not self.use_trend_filter) or (close_c > trend_c)
        trend_short_ok = (not self.use_trend_filter) or (close_c < trend_c)

        # ADX filter
        adx_ok = (not self.use_adx_filter) or (adx_c >= self.adx_thresh)

        # Standard entry conditions (EMA cross + trend filter)
        std_long = raw_long_cross and trend_long_ok
        std_short = raw_short_cross and trend_short_ok

        # Breakout entry: EMA already crossed, now price / fast EMA breaks 200 EMA
        brk_long_cross_close = (fast_p >= trend_p) and (fast_c > trend_c) or \
                               (close.iloc[prev_idx] <= trend_p and close_c > trend_c)
        brk_long = (
            self.allow_breakout
            and self.use_trend_filter
            and brk_long_cross_close
            and (fast_c > slow_c)
        )

        brk_short_cross_close = (fast_p <= trend_p) and (fast_c < trend_c) or \
                                 (close.iloc[prev_idx] >= trend_p and close_c < trend_c)
        brk_short = (
            self.allow_breakout
            and self.use_trend_filter
            and brk_short_cross_close
            and (fast_c < slow_c)
        )

        long_entry_cond = (std_long or brk_long) and adx_ok and self.allow_long
        short_entry_cond = (std_short or brk_short) and adx_ok and self.allow_short

        # ── Exits first (opposite cross) ───────────────────────────────────────
        if self.current_position == 1 and raw_short_cross:
            self.last_action_candle_ts = closed_candle_ts
            return "EXIT_LONG", (
                f"Bearish Cross: Fast {fast_c:.4f} crossed below Slow {slow_c:.4f}"
            )

        if self.current_position == -1 and raw_long_cross:
            self.last_action_candle_ts = closed_candle_ts
            return "EXIT_SHORT", (
                f"Bullish Cross: Fast {fast_c:.4f} crossed above Slow {slow_c:.4f}"
            )

        # ── Entries ────────────────────────────────────────────────────────────
        if self.allow_flip:
            # Close & reverse on same bar
            if long_entry_cond and self.current_position <= 0:
                if self.current_position < 0:
                    # Will flip: signal exit first; runner re-checks for entry
                    self.last_action_candle_ts = closed_candle_ts
                    return "EXIT_SHORT", (
                        f"Flip to Long: {fast_c:.4f} / {slow_c:.4f} "
                        f"(ADX={adx_c:.1f}, Trend={trend_c:.4f})"
                    )
                # Flat → Long
                self._set_entry_levels_long(close_c, atr_c)
                self.last_action_candle_ts = closed_candle_ts
                return "ENTRY_LONG", (
                    f"Bullish Cross/Breakout: Fast {fast_c:.4f} > Slow {slow_c:.4f} "
                    f"| ADX={adx_c:.1f} | Trend={trend_c:.4f}"
                )

            if short_entry_cond and self.current_position >= 0:
                if self.current_position > 0:
                    self.last_action_candle_ts = closed_candle_ts
                    return "EXIT_LONG", (
                        f"Flip to Short: {fast_c:.4f} / {slow_c:.4f} "
                        f"(ADX={adx_c:.1f}, Trend={trend_c:.4f})"
                    )
                # Flat → Short
                self._set_entry_levels_short(close_c, atr_c)
                self.last_action_candle_ts = closed_candle_ts
                return "ENTRY_SHORT", (
                    f"Bearish Cross/Breakout: Fast {fast_c:.4f} < Slow {slow_c:.4f} "
                    f"| ADX={adx_c:.1f} | Trend={trend_c:.4f}"
                )
        else:
            # Only enter when flat
            if self.current_position == 0:
                if long_entry_cond:
                    self._set_entry_levels_long(close_c, atr_c)
                    self.last_action_candle_ts = closed_candle_ts
                    return "ENTRY_LONG", (
                        f"Bullish Cross/Breakout: Fast {fast_c:.4f} > Slow {slow_c:.4f} "
                        f"| ADX={adx_c:.1f} | Trend={trend_c:.4f}"
                    )
                if short_entry_cond:
                    self._set_entry_levels_short(close_c, atr_c)
                    self.last_action_candle_ts = closed_candle_ts
                    return "ENTRY_SHORT", (
                        f"Bearish Cross/Breakout: Fast {fast_c:.4f} < Slow {slow_c:.4f} "
                        f"| ADX={adx_c:.1f} | Trend={trend_c:.4f}"
                    )

        return None, ""

    # ══════════════════════════════════════════════════════════════════════════
    # Position State Management
    # ══════════════════════════════════════════════════════════════════════════

    def _set_entry_levels_long(self, price: float, atr_val: float):
        self.entry_price = price
        self.last_entry_price = price
        self.tp_level = price + (atr_val * self.atr_mult_tp)
        self.trailing_stop_level = price - (atr_val * self.atr_mult_trail)
        self.partial_exit_done = False
        self.reset_milestones()
        if self.stop_loss_pct is not None:
            self.initial_sl_price = price * (1 - self.stop_loss_pct / self.leverage)
        else:
            self.initial_sl_price = None

    def _set_entry_levels_short(self, price: float, atr_val: float):
        self.entry_price = price
        self.last_entry_price = price
        self.tp_level = price - (atr_val * self.atr_mult_tp)
        self.trailing_stop_level = price + (atr_val * self.atr_mult_trail)
        self.partial_exit_done = False
        self.reset_milestones()
        if self.stop_loss_pct is not None:
            self.initial_sl_price = price * (1 + self.stop_loss_pct / self.leverage)
        else:
            self.initial_sl_price = None

    def update_position_state(
        self,
        action: str,
        current_time_ms: float,
        indicators: Any = None,
        price: float = 0.0,
        reason: str = "",
    ):
        """Update internal state after a trade action."""
        atr_val = self._resolve_atr(indicators)

        if action == "ENTRY_LONG":
            self.current_position = 1
            self._set_entry_levels_long(price, atr_val)
            self.active_trade = {
                "type": "LONG",
                "entry_time": _fmt(current_time_ms),
                "entry_price": price,
                "entry_atr": atr_val,
                "status": "OPEN",
                "logs": [],
            }
            logger.info(
                f"[{self.symbol}] ENTRY_LONG @ {price:.4f} | "
                f"TP={self.tp_level:.4f} SL={self.trailing_stop_level:.4f} "
                f"(ATR={atr_val:.4f})"
            )

        elif action == "ENTRY_SHORT":
            self.current_position = -1
            self._set_entry_levels_short(price, atr_val)
            self.active_trade = {
                "type": "SHORT",
                "entry_time": _fmt(current_time_ms),
                "entry_price": price,
                "entry_atr": atr_val,
                "status": "OPEN",
                "logs": [],
            }
            logger.info(
                f"[{self.symbol}] ENTRY_SHORT @ {price:.4f} | "
                f"TP={self.tp_level:.4f} SL={self.trailing_stop_level:.4f} "
                f"(ATR={atr_val:.4f})"
            )

        elif action == "PARTIAL_EXIT":
            self.partial_exit_done = True
            if self.active_trade:
                partial = self.active_trade.copy()
                partial["exit_time"] = _fmt(current_time_ms)
                partial["exit_price"] = price
                partial["status"] = "PARTIAL"
                partial["exit_pct"] = self.partial_pct
                entry = float(self.active_trade["entry_price"])
                partial["points"] = (
                    price - entry if self.current_position == 1 else entry - price
                )
                self.trades.append(partial)
                self.active_trade["partial_exit"] = True

        elif action == "MILESTONE_EXIT":
            milestone_idx = 0
            exit_pct = 0.0
            match = re.search(r"Milestone (\d+):", reason)
            if match:
                milestone_idx = int(match.group(1)) - 1
            if 0 <= milestone_idx < len(self.profit_milestones):
                m = self.profit_milestones[milestone_idx]
                exit_pct = m.get("exit_pct", 0.0) if isinstance(m, dict) else getattr(m, "exit_pct", 0.0)

            if self.active_trade:
                ms_trade = self.active_trade.copy()
                ms_trade["exit_time"] = _fmt(current_time_ms)
                ms_trade["exit_price"] = price
                ms_trade["status"] = f"MILESTONE_{milestone_idx + 1}"
                ms_trade["exit_pct"] = exit_pct
                entry = float(self.active_trade.get("entry_price", price))
                ms_trade["points"] = (
                    price - entry if self.current_position == 1 else entry - price
                )
                self.trades.append(ms_trade)
                self.active_trade["milestone_exit"] = True

        elif action == "EXIT_LONG":
            self.current_position = 0
            if self.active_trade:
                self.active_trade["exit_time"] = _fmt(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["status"] = "CLOSED"
                if "Trailing" in reason:
                    self.active_trade["status"] = "TRAIL STOP"
                elif "PnL Exit" in reason:
                    self.active_trade["status"] = "PNL EXIT"
                self.active_trade["points"] = price - self.active_trade["entry_price"]
                self.trades.append(self.active_trade)
                self.active_trade = None
            self._reset_trade_state()

        elif action == "EXIT_SHORT":
            self.current_position = 0
            if self.active_trade:
                self.active_trade["exit_time"] = _fmt(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["status"] = "CLOSED"
                if "Trailing" in reason:
                    self.active_trade["status"] = "TRAIL STOP"
                elif "PnL Exit" in reason:
                    self.active_trade["status"] = "PNL EXIT"
                self.active_trade["points"] = self.active_trade["entry_price"] - price
                self.trades.append(self.active_trade)
                self.active_trade = None
            self._reset_trade_state()

        self._save_to_disk()

    # ══════════════════════════════════════════════════════════════════════════
    # Backtest Loop
    # ══════════════════════════════════════════════════════════════════════════

    def run_backtest(self, df: pd.DataFrame):
        """Run a complete backtest over the provided DataFrame."""
        logger.info(f"[{self.symbol}] Starting EMA Crossover backtest...")
        prev_suppress = self._suppress_persistence
        self._suppress_persistence = True

        # Reset state
        self.trades = []
        self.current_position = 0
        self.active_trade = None
        self.entry_price = None
        self.tp_level = None
        self.trailing_stop_level = None
        self.initial_sl_price = None
        self.partial_exit_done = False
        self.reset_milestones()

        if df.empty:
            self._suppress_persistence = prev_suppress
            return

        min_len = max(self.fast_len, self.slow_len, self.trend_len, self.adx_len) + 1
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        fast_s = close.ewm(span=self.fast_len, adjust=False).mean()
        slow_s = close.ewm(span=self.slow_len, adjust=False).mean()
        trend_s = close.ewm(span=self.trend_len, adjust=False).mean()
        adx_s = self._calc_adx(df, self.adx_len)

        tr = pd.concat(
            [
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr_s = tr.ewm(span=self.atr_period, adjust=False).mean()

        for i in range(len(df)):
            if i < min_len:
                continue

            ts_ms = float(df["time"].iloc[i]) * 1000
            c = float(close.iloc[i])
            h = float(high.iloc[i])
            l = float(low.iloc[i])
            fast = float(fast_s.iloc[i])
            slow = float(slow_s.iloc[i])
            trend = float(trend_s.iloc[i])
            adx = float(adx_s.iloc[i])
            atr = float(atr_s.iloc[i])
            fast_prev = float(fast_s.iloc[i - 1])
            slow_prev = float(slow_s.iloc[i - 1])
            trend_prev = float(trend_s.iloc[i - 1])
            close_prev = float(close.iloc[i - 1])

            if pd.isna(fast) or pd.isna(slow) or pd.isna(trend) or pd.isna(atr):
                continue

            indicators = {"atr": atr, "fast": fast, "slow": slow, "trend": trend}

            # 1. Update Trailing Stop
            if self.trailing_stop_level is not None:
                if self.current_position == 1:
                    new_stop = c - (atr * self.atr_mult_trail)
                    if new_stop > self.trailing_stop_level:
                        self.trailing_stop_level = new_stop
                elif self.current_position == -1:
                    new_stop = c + (atr * self.atr_mult_trail)
                    if new_stop < self.trailing_stop_level:
                        self.trailing_stop_level = new_stop

            # 2. Fixed Hard SL (intra-candle wick)
            if self.initial_sl_price is not None:
                if self.current_position == 1 and l <= self.initial_sl_price:
                    self.update_position_state("EXIT_LONG", ts_ms, indicators, self.initial_sl_price, "Fixed SL Hit")
                    continue
                elif self.current_position == -1 and h >= self.initial_sl_price:
                    self.update_position_state("EXIT_SHORT", ts_ms, indicators, self.initial_sl_price, "Fixed SL Hit")
                    continue

            # 3. Trailing Stop Hit (candle close)
            if self.trailing_stop_level is not None:
                if self.current_position == 1 and c <= self.trailing_stop_level:
                    self.update_position_state("EXIT_LONG", ts_ms, indicators, c, "Trailing SL Hit")
                    continue
                elif self.current_position == -1 and c >= self.trailing_stop_level:
                    self.update_position_state("EXIT_SHORT", ts_ms, indicators, c, "Trailing SL Hit")
                    continue

            # 4. PnL % Exit Gate
            if self.pnl_exit_pct is not None and self.entry_price and self.current_position != 0:
                upnl = self._manual_pnl(c)
                if upnl >= self.pnl_exit_pct:
                    action_str = "EXIT_LONG" if self.current_position == 1 else "EXIT_SHORT"
                    self.update_position_state(action_str, ts_ms, indicators, c, f"PnL Exit: {upnl:.1f}%")
                    continue

            # 5. ATR Partial TP (uses intra-bar high/low)
            if self.enable_partial_tp and not self.partial_exit_done and self.tp_level is not None:
                if self.current_position == 1 and h >= self.tp_level:
                    self.update_position_state("PARTIAL_EXIT", ts_ms, indicators, self.tp_level, f"Partial TP Hit: {self.tp_level:.4f}")
                elif self.current_position == -1 and l <= self.tp_level:
                    self.update_position_state("PARTIAL_EXIT", ts_ms, indicators, self.tp_level, f"Partial TP Hit: {self.tp_level:.4f}")

            # 6. Profit Milestone Exit (uses intra-bar price)
            if self.enable_profit_milestones and self.entry_price and self.current_position != 0:
                if not self.milestone_hit:
                    for idx, milestone in enumerate(self.profit_milestones):
                        pnl_threshold = milestone["pnl_pct"]
                        exit_pct = milestone["exit_pct"]
                        if self.current_position == 1:
                            milestone_price = self.entry_price * (
                                1 + pnl_threshold / (100 * self.leverage)
                            )
                            if h >= milestone_price:
                                ms_reason = f"Milestone {idx + 1}: PnL >= {pnl_threshold}% | exit_pct={exit_pct}"
                                self.update_position_state("MILESTONE_EXIT", ts_ms, indicators, milestone_price, ms_reason)
                                self.milestone_hit = True
                                break
                        else:
                            milestone_price = self.entry_price * (
                                1 - pnl_threshold / (100 * self.leverage)
                            )
                            if l <= milestone_price:
                                ms_reason = f"Milestone {idx + 1}: PnL >= {pnl_threshold}% | exit_pct={exit_pct}"
                                self.update_position_state("MILESTONE_EXIT", ts_ms, indicators, milestone_price, ms_reason)
                                self.milestone_hit = True
                                break

            # 7. EMA Signal Logic
            raw_long_cross = (fast_prev <= slow_prev) and (fast > slow)
            raw_short_cross = (fast_prev >= slow_prev) and (fast < slow)

            trend_long_ok = (not self.use_trend_filter) or (c > trend)
            trend_short_ok = (not self.use_trend_filter) or (c < trend)
            adx_ok = (not self.use_adx_filter) or (adx >= self.adx_thresh)

            std_long = raw_long_cross and trend_long_ok
            std_short = raw_short_cross and trend_short_ok

            brk_long = (
                self.allow_breakout
                and self.use_trend_filter
                and ((fast_prev <= trend_prev and fast > trend) or (close_prev <= trend_prev and c > trend))
                and (fast > slow)
            )
            brk_short = (
                self.allow_breakout
                and self.use_trend_filter
                and ((fast_prev >= trend_prev and fast < trend) or (close_prev >= trend_prev and c < trend))
                and (fast < slow)
            )

            long_entry_cond = (std_long or brk_long) and adx_ok and self.allow_long
            short_entry_cond = (std_short or brk_short) and adx_ok and self.allow_short

            # Exit signals (opposite cross)
            if self.current_position == 1 and raw_short_cross:
                self.update_position_state("EXIT_LONG", ts_ms, indicators, c, "Bearish Cross")
                if self.allow_flip and self.allow_short and short_entry_cond:
                    self._set_entry_levels_short(c, atr)
                    self.update_position_state("ENTRY_SHORT", ts_ms, indicators, c, "Flip to Short")
                continue

            if self.current_position == -1 and raw_long_cross:
                self.update_position_state("EXIT_SHORT", ts_ms, indicators, c, "Bullish Cross")
                if self.allow_flip and self.allow_long and long_entry_cond:
                    self._set_entry_levels_long(c, atr)
                    self.update_position_state("ENTRY_LONG", ts_ms, indicators, c, "Flip to Long")
                continue

            # Entries (flat only)
            if self.current_position == 0:
                if long_entry_cond:
                    self._set_entry_levels_long(c, atr)
                    self.update_position_state("ENTRY_LONG", ts_ms, indicators, c, "Bullish Cross/Breakout")
                elif short_entry_cond:
                    self._set_entry_levels_short(c, atr)
                    self.update_position_state("ENTRY_SHORT", ts_ms, indicators, c, "Bearish Cross/Breakout")

        self._suppress_persistence = prev_suppress
        logger.info(f"[{self.symbol}] Backtest complete. Trades: {len(self.trades)}")

    # ══════════════════════════════════════════════════════════════════════════
    # Reconciliation
    # ══════════════════════════════════════════════════════════════════════════

    def reconcile_position(
        self,
        size: float,
        entry_price: float,
        current_price: float = None,
        live_pos_data: Optional[Dict] = None,
    ) -> tuple[Optional[str], str]:
        """Reconcile internal state with live exchange position."""
        import time

        expected_pos = 0
        if size > 0:
            expected_pos = 1
        elif size < 0:
            expected_pos = -1

        action = None
        reason = ""

        price_changed = (
            self.entry_price is not None
            and abs(self.entry_price - entry_price) > 0.0001
        )
        truly_new = self.current_position != 0 and self.current_position != expected_pos

        if self.current_position != expected_pos or price_changed:
            if self.current_position != expected_pos:
                logger.warning(
                    f"[{self.symbol}] Reconcile: internal={self.current_position} "
                    f"→ exchange={expected_pos} (size={size})"
                )
            if price_changed:
                logger.warning(
                    f"[{self.symbol}] Reconcile price: {self.entry_price} → {entry_price}"
                )

            if self.current_position == 0 and expected_pos != 0:
                # Cold start
                found = self._load_from_disk()
                logger.info(
                    f"Cold Start: restored={'yes' if found else 'no'} for {self.symbol}"
                )

            old_position = self.current_position
            self.current_position = expected_pos
            self.entry_price = entry_price

            if truly_new:
                self.reset_milestones()
                self.partial_exit_done = False
                clear_strategy_state(self.symbol, self.STRATEGY_KEY)

            if expected_pos == 0:
                if self.active_trade:
                    action = "EXIT_LONG" if old_position == 1 else "EXIT_SHORT"
                    reason = "External Exit (Stop-Loss or Manual)"
                    self.active_trade["exit_time"] = _fmt(time.time() * 1000) + " (Rec)"
                    self.active_trade["status"] = "CLOSED (SYNC)"
                    self.trades.append(self.active_trade)
                    self.active_trade = None
                self._reset_trade_state()
                clear_strategy_state(self.symbol, self.STRATEGY_KEY)

        if expected_pos != 0 and not self.active_trade:
            side = "LONG" if expected_pos == 1 else "SHORT"
            self.active_trade = {
                "type": side,
                "entry_time": _fmt(time.time() * 1000) + " (Rec)",
                "entry_price": entry_price,
                "status": "OPEN",
            }
            self.entry_price = entry_price
            logger.info(f"[{self.symbol}] Reconciled {side} @ {entry_price}")

        if self.current_position != 0:
            self._save_to_disk()

        return action, reason

    def set_position(self, position: int):
        self.current_position = position

    # ══════════════════════════════════════════════════════════════════════════
    # Persistence
    # ══════════════════════════════════════════════════════════════════════════

    def save_state(self, extra_data: Optional[Dict[str, Any]] = None):
        extra = {
            "partial_exit_done": self.partial_exit_done,
            "tp_level": self.tp_level,
            "initial_sl_price": self.initial_sl_price,
        }
        if extra_data:
            extra.update(extra_data)
        super().save_state(extra_data=extra)

    def _save_to_disk(self):
        if self._suppress_persistence:
            return
        if self.current_position == 0:
            self.clear_state()
            return
        extra = {
            "partial_exit_done": self.partial_exit_done,
            "milestone_hit": self.milestone_hit,
            "tp_level": self.tp_level,
            "initial_sl_price": self.initial_sl_price,
        }
        self.save_state(extra_data=extra)

    def _load_from_disk(self) -> bool:
        state = self.load_state()
        if not state:
            return False
        self.partial_exit_done = state.get("partial_exit_done", False)
        raw = state.get("milestone_hit")
        if raw is None:
            old_arr = state.get("milestones_hit", [])
            raw = bool(old_arr[0]) if old_arr else False
        self.milestone_hit = bool(raw)
        if self.tp_level is None:
            self.tp_level = state.get("tp_level")
        if self.initial_sl_price is None:
            self.initial_sl_price = state.get("initial_sl_price")
        logger.info(
            f"[{self.symbol}] State restored: Partial={self.partial_exit_done}, "
            f"Milestone={self.milestone_hit}"
        )
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # Private Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _set_entry_levels_long(self, price: float, atr: float):
        self.entry_price = price
        self.tp_level = price + (atr * self.atr_mult_tp)
        self.trailing_stop_level = price - (atr * self.atr_mult_trail)
        self.partial_exit_done = False
        self.reset_milestones()
        if self.stop_loss_pct is not None:
            self.initial_sl_price = price * (1 - self.stop_loss_pct / max(self.leverage, 1))
        else:
            self.initial_sl_price = None

    def _set_entry_levels_short(self, price: float, atr: float):
        self.entry_price = price
        self.tp_level = price - (atr * self.atr_mult_tp)
        self.trailing_stop_level = price + (atr * self.atr_mult_trail)
        self.partial_exit_done = False
        self.reset_milestones()
        if self.stop_loss_pct is not None:
            self.initial_sl_price = price * (1 + self.stop_loss_pct / max(self.leverage, 1))
        else:
            self.initial_sl_price = None

    def _reset_trade_state(self):
        self.entry_price = None
        self.tp_level = None
        self.trailing_stop_level = None
        self.partial_exit_done = False
        self.initial_sl_price = None
        self.trade_id = None
        self.reset_milestones()

    def _manual_pnl(self, current_price: float) -> float:
        """Calculate unrealised PnL % of margin from entry price."""
        if not self.entry_price or self.current_position == 0:
            return 0.0
        if self.current_position == 1:
            return (current_price - self.entry_price) / self.entry_price * self.leverage * 100
        return (self.entry_price - current_price) / self.entry_price * self.leverage * 100

    def _resolve_atr(self, indicators: Any) -> float:
        """Extract ATR from indicators dict, falling back to cached value."""
        if isinstance(indicators, dict):
            return indicators.get("atr", self.last_atr or 0.0)
        return self.last_atr or 0.0
