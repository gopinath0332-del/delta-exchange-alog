"""
BB Breakout + EMA + TTM Squeeze + RVOL + HTF Trend Filter Strategy

Strategy Logic (ported from pine/bb-breakout-ema-squeeze.pine):
- Long Entry  : Close crosses above BB Upper Band + EMA filter + Squeeze fired recently + RVOL >= threshold + HTF bullish
- Short Entry : Close crosses below BB Lower Band + EMA filter + Squeeze fired recently + RVOL >= threshold + HTF bearish
- Long Exit   : Close crosses under BB Basis (middle band), or ATR Trailing SL hit
- Short Exit  : Close crosses over BB Basis (middle band), or ATR Trailing SL hit

Filters:
1. EMA         — Close must be above (long) / below (short) EMA on current timeframe
2. TTM Squeeze — Entry allowed only within N bars after squeeze fires
                 Squeeze ON  : BB fully inside Keltner Channels (BB_upper < KC_upper AND BB_lower > KC_lower)
                 Squeeze Fire: Previous bar was squeezed, current bar is not
3. RVOL        — Relative Volume = volume / SMA(volume, N). Must be >= rvolMin
4. HTF EMA     — Simulates higher timeframe EMA by multiplying ema_length by htf_multiplier
                 (e.g. 4H EMA(50) ≈ 1H EMA(200)). Long only when close > htf_ema.

ATR Trailing Stop:
- Long : Stop ratchets UP as price rises (never pulls back down)
- Short: Stop ratchets DOWN as price falls (never pulls back up)
"""

import logging
from typing import Dict, Optional, Tuple, Any
import pandas as pd
import numpy as np
from core.config import get_config
from core.candle_utils import get_closed_candle_index
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


def _calc_atr(df: pd.DataFrame, length: int) -> pd.Series:
    """Calculate ATR using EWM (matches Pine Script ta.atr)."""
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift(1))
    low_close = np.abs(df["low"] - df["close"].shift(1))
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    # TradeView's ta.atr uses Wilder's RMA (alpha = 1/length), NOT standard EMA (span=length).
    return tr.ewm(alpha=1.0/length, adjust=False).mean()


class BBBreakoutStrategy(BaseStrategy):
    """
    Bollinger Band Breakout strategy with TTM Squeeze, RVOL, EMA & HTF filters.

    Mirrors the Pine Script bb-breakout-ema-squeeze.pine signal-for-signal.
    """

    def __init__(self, symbol: str = "ARCUSD"):
        super().__init__(symbol, "bb_breakout")
        config = get_config()
        cfg = config.settings.get("strategies", {}).get("bb_breakout", {})

        self.symbol = symbol

        # ── Core Parameters ──────────────────────────────────────────────────
        self.trade_mode = cfg.get("trade_mode", "Both")  # "Long", "Short", "Both"
        self.bb_length = cfg.get("bb_length", 20)
        self.bb_mult = cfg.get("bb_mult", 2.0)
        self.atr_length = cfg.get("atr_length", 14)
        self.atr_mult = cfg.get("atr_mult", 2.0)  # ATR trailing SL multiplier
        self.use_atr_sl = cfg.get("use_atr_sl", True)  # False = disable ATR trailing SL

        # ── EMA Filter ───────────────────────────────────────────────────────
        self.use_ema = cfg.get("use_ema", True)
        self.ema_length = cfg.get("ema_length", 100)

        # ── TTM Squeeze Filter ───────────────────────────────────────────────
        self.use_squeeze = cfg.get("use_squeeze", True)
        self.kc_mult = cfg.get("kc_mult", 1.5)       # Keltner Channel width
        self.squeeze_window = cfg.get("squeeze_window", 10)  # Bars after fire allowed

        # ── RVOL Filter ──────────────────────────────────────────────────────
        self.use_volume = cfg.get("use_volume", True)
        self.vol_length = cfg.get("vol_length", 20)
        self.rvol_min = cfg.get("rvol_min", 1.5)

        # ── HTF Trend Filter ─────────────────────────────────────────────────
        # Simulated by using ema_length * htf_multiplier on the same 1H data.
        # e.g. htf_multiplier=4, htf_ema_length=50 → 1H EMA(200) ≈ 4H EMA(50)
        self.use_htf = cfg.get("use_htf", True)
        self.htf_ema_length = cfg.get("htf_ema_length", 100)  # Matches Pine htfLength=100
        self.htf_multiplier = cfg.get("htf_multiplier", 4)  # 4 = 4H on 1H data

        # ── Mode Flags ───────────────────────────────────────────────────────
        self.allow_long = self.trade_mode in ["Long", "Both"]
        self.allow_short = self.trade_mode in ["Short", "Both"]

        # ── Dashboard / Runner interface ──────────────────────────────────────
        self.indicator_label = "BB"
        self.timeframe = "1h"
        self.leverage: int = 1

        # ── Squeeze Window Tracking ───────────────────────────────────────────
        # Computed statelessly during check_signals based on series history.

        # ── Persistence ───────────────────────────────────────────────────────
        self.load_state()

        # ── Indicator Cache (dashboard) ───────────────────────────────────────
        self.last_upper = 0.0
        self.last_lower = 0.0
        self.last_basis = 0.0
        self.last_atr = 0.0
        self.last_ema = 0.0
        self.last_htf_ema = 0.0
        self.last_rvol = 0.0
        self.last_squeeze = False   # True = currently in squeeze

        # ── Trade History ─────────────────────────────────────────────────────
        self.trades = []
        self.active_trade = None

        # ── One-action-per-candle guard ───────────────────────────────────────
        self.last_action_candle_ts = None

        logger.info(
            f"BBBreakoutStrategy initialized for {symbol}: "
            f"Mode={self.trade_mode}, BB={self.bb_length}/{self.bb_mult}, "
            f"ATR={self.atr_length}*{self.atr_mult}, EMA={self.ema_length}, "
            f"KC={self.kc_mult}, SqWindow={self.squeeze_window}, "
            f"RVOL>={self.rvol_min}, HTF={self.use_htf} (x{self.htf_multiplier}*EMA{self.htf_ema_length})"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Indicator Calculations
    # ─────────────────────────────────────────────────────────────────────────

    def _calc_htf_ema_length(self) -> int:
        """Return the 1H EMA length that approximates the HTF EMA."""
        return self.htf_ema_length * self.htf_multiplier

    def calculate_indicators(
        self, df: pd.DataFrame, current_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate all indicators and cache values for the dashboard.

        Returns a dict with keys: upper, lower, basis, atr, ema, htf_ema, rvol, is_squeeze
        """
        result = {
            "upper": 0.0, "lower": 0.0, "basis": 0.0,
            "atr": 0.0, "ema": 0.0, "htf_ema": 0.0,
            "rvol": 0.0, "is_squeeze": False,
        }

        min_len = max(self.bb_length, self.atr_length, self.ema_length,
                      self.vol_length, self._calc_htf_ema_length()) + 2
        if len(df) < min_len:
            return result

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        volume = df["volume"].astype(float) if "volume" in df.columns else pd.Series(
            np.ones(len(df)), index=df.index
        )

        # Bollinger Bands
        basis = close.rolling(self.bb_length).mean()
        dev = close.rolling(self.bb_length).std(ddof=0) * self.bb_mult
        upper = basis + dev
        lower = basis - dev

        # ATR
        atr_series = _calc_atr(df, self.atr_length)
        
        # New: Standardized ATR for Global Risk-Based Sizing
        self._calculate_atr(df, self.atr_length)

        # Keltner Channels (using same basis as BB)
        kc_upper = basis + self.kc_mult * atr_series
        kc_lower = basis - self.kc_mult * atr_series

        # TTM Squeeze state
        is_squeeze_series = (upper < kc_upper) & (lower > kc_lower)

        # EMA (current TF)
        ema_series = close.ewm(span=self.ema_length, adjust=False).mean()

        # HTF EMA (simulated)
        htf_len = self._calc_htf_ema_length()
        htf_ema_series = close.ewm(span=htf_len, adjust=False).mean()

        # RVOL
        vol_ma = volume.rolling(self.vol_length).mean()
        rvol_series = volume / vol_ma.replace(0, np.nan)

        # Cache latest values
        self.last_upper = float(upper.iloc[-1])
        self.last_lower = float(lower.iloc[-1])
        self.last_basis = float(basis.iloc[-1])
        self.last_atr = float(atr_series.iloc[-1])
        self.last_ema = float(ema_series.iloc[-1])
        self.last_htf_ema = float(htf_ema_series.iloc[-1])
        self.last_rvol = float(rvol_series.iloc[-1]) if not pd.isna(rvol_series.iloc[-1]) else 0.0
        self.last_squeeze = bool(is_squeeze_series.iloc[-1])

        result.update({
            "upper": self.last_upper,
            "lower": self.last_lower,
            "basis": self.last_basis,
            "atr": self.last_atr,
            "ema": self.last_ema,
            "htf_ema": self.last_htf_ema,
            "rvol": self.last_rvol,
            "is_squeeze": self.last_squeeze,
        })
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Signal Detection
    # ─────────────────────────────────────────────────────────────────────────

    def check_signals(
        self,
        df: pd.DataFrame,
        current_time_ms: float,
        live_pos_data: Optional[Dict] = None,
    ) -> Tuple[Optional[str], str]:
        """
        Evaluate closed-candle signals.

        Returns (action, reason). Action is one of:
          ENTRY_LONG, ENTRY_SHORT, EXIT_LONG, EXIT_SHORT, or None.
        """
        min_len = max(self.bb_length, self.atr_length, self.ema_length,
                      self.vol_length, self._calc_htf_ema_length()) + 3
        if df.empty or len(df) < min_len:
            return None, ""

        current_time_s = current_time_ms / 1000.0
        self.calculate_indicators(df, current_time=current_time_s)

        closed_idx = get_closed_candle_index(df, current_time_ms, self.timeframe)

        # One-action-per-candle rule
        closed_candle_ts = df["time"].iloc[closed_idx]
        if (
            self.last_action_candle_ts is not None
            and closed_candle_ts <= self.last_action_candle_ts
        ):
            return None, f"One action per candle: already acted on {closed_candle_ts}"

        prev_idx = closed_idx - 1

        # ── Per-bar indicator values at the CLOSED candle ──────────────────
        close_s = df["close"].astype(float)
        high_s = df["high"].astype(float)
        low_s = df["low"].astype(float)
        volume_s = (
            df["volume"].astype(float)
            if "volume" in df.columns
            else pd.Series(np.ones(len(df)), index=df.index)
        )

        # Bollinger Bands
        basis_s = close_s.rolling(self.bb_length).mean()
        dev_s = close_s.rolling(self.bb_length).std(ddof=0) * self.bb_mult
        upper_s = basis_s + dev_s
        lower_s = basis_s - dev_s

        # ATR
        atr_s = _calc_atr(df, self.atr_length)

        # Keltner Channels
        kc_upper_s = basis_s + self.kc_mult * atr_s
        kc_lower_s = basis_s - self.kc_mult * atr_s

        # TTM Squeeze per-bar
        squeeze_s = (upper_s < kc_upper_s) & (lower_s > kc_lower_s)
        
        # Squeeze fire event: it WAS squeeze on previous bar, and is NOT squeeze on current bar
        was_squeeze_s = squeeze_s.shift(1).fillna(False)
        squeeze_fired_s = was_squeeze_s & ~squeeze_s
        
        # Emulate Pine Script ta.barssince()
        bars_since = 999
        for i in range(0, self.squeeze_window + 1):
            valid_idx = closed_idx - i
            if valid_idx >= 0 and squeeze_fired_s.iloc[valid_idx]:
                bars_since = i
                break
                
        # Update dashboard state
        self._bars_since_squeeze_fire = bars_since
        recent_release = bars_since <= self.squeeze_window

        # EMA
        ema_s = close_s.ewm(span=self.ema_length, adjust=False).mean()
        ema_closed = float(ema_s.iloc[closed_idx])

        # HTF EMA
        htf_len = self._calc_htf_ema_length()
        htf_ema_s = close_s.ewm(span=htf_len, adjust=False).mean()
        htf_ema_closed = float(htf_ema_s.iloc[closed_idx])

        # RVOL
        vol_ma_s = volume_s.rolling(self.vol_length).mean()
        rvol_s = volume_s / vol_ma_s.replace(0, np.nan)
        rvol_closed = float(rvol_s.iloc[closed_idx]) if not pd.isna(rvol_s.iloc[closed_idx]) else 0.0
        high_volume = rvol_closed >= self.rvol_min

        # Closed and previous candle values
        close_closed = float(close_s.iloc[closed_idx])
        upper_closed = float(upper_s.iloc[closed_idx])
        lower_closed = float(lower_s.iloc[closed_idx])
        basis_closed = float(basis_s.iloc[closed_idx])
        upper_prev = float(upper_s.iloc[prev_idx])
        lower_prev = float(lower_s.iloc[prev_idx])
        basis_prev = float(basis_s.iloc[prev_idx])
        close_prev = float(close_s.iloc[prev_idx])
        atr_closed = float(atr_s.iloc[closed_idx])

        # Current live price (for trailing SL evaluation)
        current_price = float(close_s.iloc[-1])

        # ── Trailing Stop Check (ratchet, closed-candle logic) ─────────────
        if self.use_atr_sl and self.trailing_stop_level is not None:
            if self.current_position == 1:
                new_stop = close_closed - atr_closed * self.atr_mult
                if new_stop > self.trailing_stop_level:
                    self.trailing_stop_level = new_stop
                    self.save_state()  # Persist ratcheted stop
                if close_closed <= self.trailing_stop_level:
                    self.last_action_candle_ts = closed_candle_ts
                    return "EXIT_LONG", (
                        f"ATR Trailing SL hit: {close_closed:.6f} <= {self.trailing_stop_level:.6f}"
                    )
            elif self.current_position == -1:
                new_stop = close_closed + atr_closed * self.atr_mult
                if new_stop < self.trailing_stop_level:
                    self.trailing_stop_level = new_stop
                    self.save_state()  # Persist ratcheted stop
                if close_closed >= self.trailing_stop_level:
                    self.last_action_candle_ts = closed_candle_ts
                    return "EXIT_SHORT", (
                        f"ATR Trailing SL hit: {close_closed:.6f} >= {self.trailing_stop_level:.6f}"
                    )

        # ── BB Basis Exit (closed candle cross) ───────────────────────────
        # Long exits when close crosses UNDER the BB Basis
        long_exit = close_prev >= basis_prev and close_closed < basis_closed
        # Short exits when close crosses OVER the BB Basis
        short_exit = close_prev <= basis_prev and close_closed > basis_closed

        if self.current_position == 1 and long_exit:
            self.last_action_candle_ts = closed_candle_ts
            return "EXIT_LONG", (
                f"Close {close_closed:.6f} crossed under BB Basis {basis_closed:.6f}"
            )

        if self.current_position == -1 and short_exit:
            self.last_action_candle_ts = closed_candle_ts
            return "EXIT_SHORT", (
                f"Close {close_closed:.6f} crossed over BB Basis {basis_closed:.6f}"
            )

        # ── BB Breakout Entry (closed candle crossover) ───────────────────
        # Long: close crossed ABOVE BB Upper
        long_breakout = close_prev <= upper_prev and close_closed > upper_closed
        # Short: close crossed BELOW BB Lower
        short_breakout = close_prev >= lower_prev and close_closed < lower_closed

        # ── Apply Filters ─────────────────────────────────────────────────
        ema_long_ok = (not self.use_ema) or (close_closed > ema_closed)
        ema_short_ok = (not self.use_ema) or (close_closed < ema_closed)
        squeeze_ok = (not self.use_squeeze) or recent_release
        volume_ok = (not self.use_volume) or high_volume
        htf_long_ok = (not self.use_htf) or (close_closed > htf_ema_closed)
        htf_short_ok = (not self.use_htf) or (close_closed < htf_ema_closed)

        filter_detail = (
            f"EMA={ema_closed:.4f}, HTF_EMA={htf_ema_closed:.4f}, "
            f"RVOL={rvol_closed:.2f}x, SqBars={self._bars_since_squeeze_fire}"
        )

        # ── Entry Logic ───────────────────────────────────────────────────
        if self.current_position == 0:
            if self.allow_long and long_breakout and ema_long_ok and squeeze_ok and volume_ok and htf_long_ok:
                self.entry_price = close_closed
                if self.use_atr_sl:
                    self.trailing_stop_level = close_closed - atr_closed * self.atr_mult
                self.last_action_candle_ts = closed_candle_ts
                return "ENTRY_LONG", (
                    f"BB Upper Breakout: Close {close_closed:.6f} > Upper {upper_closed:.6f} | "
                    f"{filter_detail}"
                )

            if self.allow_short and short_breakout and ema_short_ok and squeeze_ok and volume_ok and htf_short_ok:
                self.entry_price = close_closed
                if self.use_atr_sl:
                    self.trailing_stop_level = close_closed + atr_closed * self.atr_mult
                self.last_action_candle_ts = closed_candle_ts
                return "ENTRY_SHORT", (
                    f"BB Lower Breakdown: Close {close_closed:.6f} < Lower {lower_closed:.6f} | "
                    f"{filter_detail}"
                )

        return None, ""

    # ─────────────────────────────────────────────────────────────────────────
    # State Management
    # ─────────────────────────────────────────────────────────────────────────

    def update_position_state(
        self,
        action: str,
        current_time_ms: float,
        indicators: Any = None,
        price: float = 0.0,
        reason: str = "",
    ):
        """Update internal position state after a confirmed trade action."""
        import datetime

        def fmt(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms / 1000).strftime("%d-%m-%y %H:%M")

        if action == "ENTRY_LONG":
            self.current_position = 1
            self.last_entry_price = price
            self.entry_price = price
            # Set trailing SL from actual execution price
            self.trailing_stop_level = price - self.last_atr * self.atr_mult if self.use_atr_sl else None
            self.active_trade = {
                "type": "LONG",
                "entry_time": fmt(current_time_ms),
                "entry_price": price,
                "entry_bb": f"{self.last_upper:.4f}/{self.last_lower:.4f}",
                "status": "OPEN",
                "logs": [],
            }
            _tsl = f"{self.trailing_stop_level:.6f}" if self.trailing_stop_level is not None else "DISABLED"
            logger.debug(f"State: ENTRY_LONG @ {price}, TSL={_tsl}")
            self.save_state()

        elif action == "ENTRY_SHORT":
            self.current_position = -1
            self.last_entry_price = price
            self.entry_price = price
            self.trailing_stop_level = price + self.last_atr * self.atr_mult if self.use_atr_sl else None
            self.active_trade = {
                "type": "SHORT",
                "entry_time": fmt(current_time_ms),
                "entry_price": price,
                "entry_bb": f"{self.last_upper:.4f}/{self.last_lower:.4f}",
                "status": "OPEN",
                "logs": [],
            }
            _tsl = f"{self.trailing_stop_level:.6f}" if self.trailing_stop_level is not None else "DISABLED"
            logger.debug(f"State: ENTRY_SHORT @ {price}, TSL={_tsl}")
            self.save_state()

        elif action == "MILESTONE_EXIT":
            if self.active_trade:
                import re
                milestone_idx = 0
                exit_pct = 0.0
                match = re.search(r"Milestone (\d+):", reason)
                if match:
                    milestone_idx = int(match.group(1)) - 1
                
                if 0 <= milestone_idx < len(self.profit_milestones):
                    milestone = self.profit_milestones[milestone_idx]
                    exit_pct = milestone.get("exit_pct", 0.0) if isinstance(milestone, dict) else getattr(milestone, "exit_pct", 0.0)
                    self.milestones_hit[milestone_idx] = True

                milestone_trade = self.active_trade.copy()
                milestone_trade["exit_time"] = fmt(current_time_ms)
                milestone_trade["exit_price"] = price
                milestone_trade["status"] = f"MILESTONE_{milestone_idx + 1}"
                milestone_trade["exit_pct"] = exit_pct
                entry = float(self.active_trade.get('entry_price', price))
                milestone_trade["points"] = price - entry if self.current_position == 1 else entry - price
                self.trades.append(milestone_trade)
                self.active_trade["milestone_exit"] = True
                self.save_state()

        elif action == "EXIT_LONG":
            self.current_position = 0
            if self.active_trade:
                self.active_trade["exit_time"] = fmt(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["status"] = "CLOSED"
                if "Trailing" in reason:
                    self.active_trade["status"] = "TRAIL STOP"
                elif "Basis" in reason or "crossed under" in reason:
                    self.active_trade["status"] = "BASIS EXIT"
                self.active_trade["points"] = price - float(self.active_trade["entry_price"])
                self.trades.append(self.active_trade)
                self.active_trade = None
            self._reset_trade_state()
            self.clear_state()

        elif action == "EXIT_SHORT":
            self.current_position = 0
            if self.active_trade:
                self.active_trade["exit_time"] = fmt(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["status"] = "CLOSED"
                if "Trailing" in reason:
                    self.active_trade["status"] = "TRAIL STOP"
                elif "Basis" in reason or "crossed over" in reason:
                    self.active_trade["status"] = "BASIS EXIT"
                self.active_trade["points"] = float(self.active_trade["entry_price"]) - price
                self.trades.append(self.active_trade)
                self.active_trade = None
            self._reset_trade_state()
            self.clear_state()

    def _reset_trade_state(self):
        """Clear per-trade state after a position is closed."""
        self.entry_price = None
        self.trailing_stop_level = None

    def set_position(self, position: int):
        """Force-set internal position state."""
        self.current_position = position

    def reconcile_position(
        self,
        size: float,
        entry_price: float,
        current_price: float = None,
        live_pos_data: Optional[Dict] = None,
    ):
        """Reconcile internal state with the exchange live position."""
        import time, datetime

        def fmt(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms / 1000).strftime("%d-%m-%y %H:%M")

        expected = 0
        if size > 0:
            expected = 1
        elif size < 0:
            expected = -1

        if self.current_position != expected:
            logger.warning(
                f"[{self.symbol}] Reconciling position: "
                f"internal={self.current_position} → exchange={expected} (size={size})"
            )
            self.current_position = expected

            if expected != 0 and not self.active_trade:
                side = "LONG" if expected == 1 else "SHORT"
                self.active_trade = {
                    "type": side,
                    "entry_time": fmt(time.time() * 1000) + " (Rec)",
                    "entry_price": entry_price,
                    "status": "OPEN",
                }
                self.entry_price = entry_price
                # Reconstruct trailing stop so it's not None after restart
                if self.trailing_stop_level is None and entry_price:
                    if expected == 1:
                        self.trailing_stop_level = entry_price - self.last_atr * self.atr_mult
                    else:
                        self.trailing_stop_level = entry_price + self.last_atr * self.atr_mult
                logger.info(f"Reconciled active {side} trade @ {entry_price}, TSL={self.trailing_stop_level}")

            elif expected == 0 and self.active_trade:
                self.active_trade["exit_time"] = fmt(time.time() * 1000) + " (Rec)"
                self.active_trade["status"] = "CLOSED (SYNC)"
                self.trades.append(self.active_trade)
                self.active_trade = None
                self._reset_trade_state()
                self.clear_state()
                logger.info("Reconciled: position closed externally.")

    # ─────────────────────────────────────────────────────────────────────────
    # Backtest Warmup
    # ─────────────────────────────────────────────────────────────────────────

    def _update_bars_per_day(self, timeframe: str):
        """Update timeframe (runner calls this after init)."""
        self.timeframe = timeframe
        logger.info(f"BBBreakoutStrategy timeframe set to {timeframe}")

    def run_backtest(self, df: pd.DataFrame):
        """Warmup backtest on historical data to initialise state."""
        logger.info(f"[{self.symbol}] Starting BB Breakout backtest warmup...")
        self.trades = []
        self.current_position = 0
        self.active_trade = None
        self._reset_trade_state()
        self._bars_since_squeeze_fire = 999

        if df.empty:
            return

        close_s = df["close"].astype(float)
        high_s = df["high"].astype(float)
        low_s = df["low"].astype(float)
        volume_s = (
            df["volume"].astype(float)
            if "volume" in df.columns
            else pd.Series(np.ones(len(df)), index=df.index)
        )

        # Pre-calculate all series
        basis_s = close_s.rolling(self.bb_length).mean()
        dev_s = close_s.rolling(self.bb_length).std(ddof=0) * self.bb_mult
        upper_s = basis_s + dev_s
        lower_s = basis_s - dev_s
        atr_s = _calc_atr(df, self.atr_length)
        kc_upper_s = basis_s + self.kc_mult * atr_s
        kc_lower_s = basis_s - self.kc_mult * atr_s
        squeeze_s = (upper_s < kc_upper_s) & (lower_s > kc_lower_s)
        ema_s = close_s.ewm(span=self.ema_length, adjust=False).mean()
        htf_ema_s = close_s.ewm(span=self._calc_htf_ema_length(), adjust=False).mean()
        vol_ma_s = volume_s.rolling(self.vol_length).mean()
        rvol_s = volume_s / vol_ma_s.replace(0, np.nan)

        min_i = max(
            self.bb_length, self.atr_length, self.ema_length,
            self.vol_length, self._calc_htf_ema_length()
        ) + 2

        for i in range(min_i, len(df)):
            current_time_ms = df["time"].iloc[i] * 1000

            close = float(close_s.iloc[i])
            upper = float(upper_s.iloc[i])
            lower = float(lower_s.iloc[i])
            basis = float(basis_s.iloc[i])
            atr = float(atr_s.iloc[i])
            ema = float(ema_s.iloc[i])
            htf_ema = float(htf_ema_s.iloc[i])
            rvol = float(rvol_s.iloc[i]) if not pd.isna(rvol_s.iloc[i]) else 0.0

            close_prev = float(close_s.iloc[i - 1])
            upper_prev = float(upper_s.iloc[i - 1])
            lower_prev = float(lower_s.iloc[i - 1])
            basis_prev = float(basis_s.iloc[i - 1])

            sq = bool(squeeze_s.iloc[i])
            sq_prev = bool(squeeze_s.iloc[i - 1])
            if sq_prev and not sq:
                self._bars_since_squeeze_fire = 0
            else:
                self._bars_since_squeeze_fire += 1

            recent_release = self._bars_since_squeeze_fire <= self.squeeze_window
            high_volume = rvol >= self.rvol_min
            
            # Update last known values for update_position_state
            self.last_atr = atr
            self.last_upper = upper
            self.last_lower = lower

            # ── Profit Milestone Check ─────────────────────────────────────
            if self.enable_profit_milestones and self.entry_price and self.current_position != 0:
                # Use high/low for the current bar to detect intra-bar hits
                bar_high = float(df["high"].iloc[i])
                bar_low = float(df["low"].iloc[i])
                
                for idx, milestone in enumerate(self.profit_milestones):
                    if self.milestones_hit[idx]:
                        continue
                        
                    pnl_threshold = milestone["pnl_pct"]
                    if self.current_position == 1:
                        # Long milestone price
                        milestone_price = self.entry_price * (1 + pnl_threshold / (100 * self.leverage))
                        if bar_high >= milestone_price:
                            reason = f"Milestone {idx + 1}: PnL >= {pnl_threshold}% | exit_pct={milestone['exit_pct']}"
                            self.update_position_state("MILESTONE_EXIT", current_time_ms, None, milestone_price, reason)
                            break # Only one milestone per bar
                    else:
                        # Short milestone price
                        milestone_price = self.entry_price * (1 - pnl_threshold / (100 * self.leverage))
                        if bar_low <= milestone_price:
                            reason = f"Milestone {idx + 1}: PnL >= {pnl_threshold}% | exit_pct={milestone['exit_pct']}"
                            self.update_position_state("MILESTONE_EXIT", current_time_ms, None, milestone_price, reason)
                            break # Only one milestone per bar

            # ── Trailing Stop Ratchet ──────────────────────────────────────
            if self.use_atr_sl and self.trailing_stop_level is not None:
                if self.current_position == 1:
                    new_stop = close - atr * self.atr_mult
                    if new_stop > self.trailing_stop_level:
                        self.trailing_stop_level = new_stop
                elif self.current_position == -1:
                    new_stop = close + atr * self.atr_mult
                    if new_stop < self.trailing_stop_level:
                        self.trailing_stop_level = new_stop

            # ── Trailing Stop Exit ─────────────────────────────────────────
            if self.use_atr_sl and self.trailing_stop_level is not None:
                if self.current_position == 1 and close <= self.trailing_stop_level:
                    self.update_position_state(
                        "EXIT_LONG", current_time_ms, None, close, "Trailing SL Hit"
                    )
                    continue
                elif self.current_position == -1 and close >= self.trailing_stop_level:
                    self.update_position_state(
                        "EXIT_SHORT", current_time_ms, None, close, "Trailing SL Hit"
                    )
                    continue

            # ── Basis Exit ─────────────────────────────────────────────────
            long_exit = close_prev >= basis_prev and close < basis
            short_exit = close_prev <= basis_prev and close > basis

            if self.current_position == 1 and long_exit:
                self.update_position_state(
                    "EXIT_LONG", current_time_ms, None, close,
                    f"Crossed under Basis {basis:.6f}"
                )
                continue

            if self.current_position == -1 and short_exit:
                self.update_position_state(
                    "EXIT_SHORT", current_time_ms, None, close,
                    f"Crossed over Basis {basis:.6f}"
                )
                continue

            # ── Entry Logic ────────────────────────────────────────────────
            long_breakout = close_prev <= upper_prev and close > upper
            short_breakout = close_prev >= lower_prev and close < lower

            ema_long_ok = (not self.use_ema) or (close > ema)
            ema_short_ok = (not self.use_ema) or (close < ema)
            squeeze_ok = (not self.use_squeeze) or recent_release
            volume_ok = (not self.use_volume) or high_volume
            htf_long_ok = (not self.use_htf) or (close > htf_ema)
            htf_short_ok = (not self.use_htf) or (close < htf_ema)

            if self.current_position == 0:
                if self.allow_long and long_breakout and ema_long_ok and squeeze_ok and volume_ok and htf_long_ok:
                    self.update_position_state(
                        "ENTRY_LONG", current_time_ms, None, close,
                        f"BB Breakout Long + all filters"
                    )
                    self.entry_price = close
                    if self.use_atr_sl:
                        self.trailing_stop_level = close - atr * self.atr_mult

                elif self.allow_short and short_breakout and ema_short_ok and squeeze_ok and volume_ok and htf_short_ok:
                    self.update_position_state(
                        "ENTRY_SHORT", current_time_ms, None, close,
                        f"BB Breakdown Short + all filters"
                    )
                    self.entry_price = close
                    if self.use_atr_sl:
                        self.trailing_stop_level = close + atr * self.atr_mult

        logger.info(
            f"[{self.symbol}] BB Breakout warmup complete. "
            f"Trades: {len(self.trades)}, Pos: {self.current_position}"
        )
