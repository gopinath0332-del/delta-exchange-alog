# Backtest Improvement Roadmap

Improvements are grouped by priority. Each item includes the affected file(s) and a brief description of the change required.

---

## High Priority

### 1. Leverage Simulation
**Files:** `backtest/engine.py`, `config/settings.yaml`

Currently all trades assume 100% margin (1× effective leverage). Live strategies use e.g. 5× (`LEVERAGE_RIVER=5` in `.env`), so backtest PnL is severely understated.

**Fix:** Apply leverage to position sizing in `engine.py`:
```python
position_size = (trade_capital * leverage) / entry_price
```
Add `leverage` field to backtest config in `settings.yaml` (default `1` for backward compatibility). Pass it through `BacktestEngine.__init__`.

---

### 2. Funding Rate Cost
**Files:** `backtest/engine.py`, `config/settings.yaml`

Perpetual futures charge a funding rate every 8 hours. A long position held 3 days pays ~6 funding payments. This is not modelled at all — strategies appear more profitable in backtests than they will be live.

**Fix:** Add a configurable `funding_rate_per_8h` (e.g. `0.0001` = 0.01%) in `settings.yaml`. In `engine.py`, when closing a trade, compute:
```python
holding_hours = (exit_time - entry_time).total_seconds() / 3600
funding_payments = int(holding_hours / 8)
funding_cost = position_notional * funding_rate_per_8h * funding_payments
pnl -= funding_cost
```
Show funding cost as a separate column in the trades table.

---

### 3. Realistic Slippage / Spread
**Files:** `backtest/engine.py`, `config/settings.yaml`

Entry and exit assume exact candle close price. In reality, market orders fill with a spread/slippage on top of commission. This makes entries look cheaper and exits look better than live.

**Fix:** Add a configurable `slippage_pct` per symbol tier in `settings.yaml` (e.g. `0.05%` liquid, `0.2%` illiquid). Apply directionally:
- Long entry: `fill_price = close * (1 + slippage_pct)`
- Long exit: `fill_price = close * (1 - slippage_pct)`
- Short entry/exit: reversed

---

### 4. Partial TP Tracking Bug
**Files:** `backtest/engine.py` line 87

If two trades of the same type open at the same candle timestamp, `partial_remaining_size_map` uses key `"{type}_{entry_time}"`, causing a key collision — the second trade's remaining 50% is lost.

**Fix:** Use a unique trade ID (e.g. incrementing counter) as the map key instead of `type+time`.

---

## Medium Priority

### 5. Live Equity Curve (Open PnL During Trades)
**Files:** `backtest/engine.py` lines 171–174, `backtest/metrics.py`

The equity curve only updates when a trade closes. Open unrealized PnL is invisible — the chart shows a flat line during any open position.

**Fix:** After each candle, compute mark-to-market PnL for any open position using the current candle's close price. Add an equity snapshot point for each candle, not just on close.

---

### 6. Daily Equity Snapshots for Sharpe / Sortino
**Files:** `backtest/metrics.py` lines 99–105

Sharpe and Sortino are computed from per-trade returns, then annualized to 365 days regardless of how sparse the trades are. This overstates risk-adjusted return for low-frequency strategies.

**Fix:** Build a calendar-day equity series (interpolate between trade closes). Compute daily log returns, then annualize with `√365`.

---

### 7. Trades Tab — Milestone / Partial Exit Type Display
**Files:** `backtest/templates/report_template.html`

The trades table only renders `LONG` and `SHORT` as the type. Milestone partial exits (`LONG (Partial)`) are not shown — they appear blank or missing in the UI.

**Fix:** Update the trades table column to display the full `status` field from each trade dict, which already contains `"LONG (Partial)"`, `"SHORT (Partial)"` etc.

---

### 8. Walk-Forward / Out-of-Sample Split
**Files:** `run_backtest.py`, `backtest/engine.py`

Single backtest on all available data will overfit. A walk-forward split would show whether the strategy generalises to unseen data.

**Fix:** Add CLI flags `--is-end-date` (in-sample cutoff) to `run_backtest.py`. Run two backtests per file — in-sample and out-of-sample — and render both equity curves on the same HTML report for visual comparison.

---

## Lower Priority

### 9. Commission Tiers (Maker vs. Taker)
**Files:** `backtest/engine.py`, `config/settings.yaml`

Delta charges different rates for maker (limit) and taker (market) orders (e.g. 0.02% vs 0.05%). Currently all trades pay the same flat `commission: 0.0006`.

**Fix:** Add `maker_commission` and `taker_commission` to `settings.yaml`. Entry signals via limit orders use maker rate; stop/trailing exits use taker rate.

---

### 10. Consecutive Trade Analysis (Streak Tracking)
**Files:** `backtest/metrics.py`

No win-streak or loss-streak tracking. This is useful for identifying regime sensitivity (e.g. strategy wins in trending markets, loses in ranging ones).

**Fix:** Add to metrics: `max_consecutive_wins`, `max_consecutive_losses`, `avg_consecutive_wins`, `avg_consecutive_losses`. Display in the Metrics tab.

---

### 11. Benchmark Correlation / Beta
**Files:** `backtest/metrics.py`, `backtest/reporter.py`

The buy-and-hold comparison uses the same symbol's returns. There is no BTC benchmark, beta, alpha, or market correlation.

**Fix:** Accept an optional `--benchmark` CSV path in `run_backtest.py`. Compute Pearson correlation, beta (covariance/variance), and alpha (strategy return − beta × benchmark return) against it. Add a "Benchmark" section to the Metrics tab.

---

## Status

| # | Improvement | Status |
|---|-------------|--------|
| 1 | Leverage simulation | ✅ Done |
| 2 | Funding rate cost | ⬜ Pending |
| 3 | Slippage / spread | ⬜ Pending |
| 4 | Partial TP tracking bug | ✅ Done |
| 5 | Live equity curve | ✅ Done |
| 6 | Daily Sharpe/Sortino | ⬜ Pending |
| 7 | Milestone exit display | ✅ Done |
| 8 | Walk-forward split | ⬜ Pending |
| 9 | Commission tiers | ⬜ Pending |
| 10 | Streak tracking | ⬜ Pending |
| 11 | Benchmark correlation | ⬜ Pending |
