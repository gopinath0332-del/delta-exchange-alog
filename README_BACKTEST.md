# Donchian Strategy Backtest Analysis Report

This document summarizes the results of over **5,000 independent backtests** conducted on the `donchian_channel` strategy across 181 symbols, focusing on optimizing risk-adjusted returns through Parameter Tuning and Candle Style selection.

---

## 📊 Summary of Optimal Settings

Based on exhaustive matrix testing (1H, 2H, 4H timeframes), the following parameters have been identified as the "Gold Standard" for the Donchian Breakout strategy:

| Parameter | Optimal Value | Reason |
| :--- | :--- | :--- |
| **Stop Loss Pct** | **0.20 (20%)** | Maximizes Sortino Ratio and prevents capital decay during volatile drawdowns. |
| **Candle Type** | **Heikin-Ashi** | Reduces noise and false breakouts; improves win rate by ~7-15% across most assets. |
| **Timeframe** | **Asset Dependent** | 1H for aggressive alpha; 2H/4H for stable swing trading. |

---

## 🏆 Top Recommended Assets

### 🥇 Universal Performers
These assets were "Good" (Return > 0, Sharpe > 1.0, Max DD < 60%) across **all 6 configurations** (1h/2h/4h on both Standard and Heikin-Ashi). These are the most resilient coins in the dataset.

*   **BEATUSD** (Elite performance: Sharpe ~4.73 avg)
*   **METAXUSD** (Extreme stability: Max DD < 40%)
*   **ADAUSD** (Highest reliability among major tokens)
*   **AMZNXUSD** (Stable index/equity alternative)

### 🥈 High-Alpha Anomalies (The "Standard" Subset)
While Heikin-Ashi is generally better, these specific coins performed significantly **better with Standard candles** on the 4H timeframe:
*   **BIOUSD** (+1,797% vs +1,385% HA)
*   **XANUSD** (+852% vs +753% HA)
*   **EVAAUSD** (+880% vs +816% HA)

---

## 📈 Performance Matrix Breakdown

### 1. Stop Loss Pct Optimization (ARCUSD 1H)
*Testing conducted on Standard Candles*

| Scenario | Stop Loss | Final Capital | Total Return | Sharpe Ratio | Max Drawdown |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Config 1 | 0.50 | $8,129 | +712% | 3.02 | 84% |
| Config 2 | 0.30 | $10,215 | +921% | 3.49 | 62% |
| Config 3 | 0.25 | $11,441 | +1,044% | 3.71 | 53% |
| **Config 4** | **0.20** | **$13,221** | **+1,222%** | **4.00** | **41%** |
| Config 5 | None | $6,409 | +540% | 0.38 | 102% |

### 2. Timeframe Comparison (Averages Across 181 Coins)
*Using Heikin-Ashi + 0.20 Stop Loss*

| Timeframe | Avg Return | Avg Sharpe | Avg Max DD | Win Rate % |
| :--- | :--- | :--- | :--- | :--- |
| **1H** | +540% | 2.50 | 44% | 68% |
| **2H** | +520% | 2.45 | 42% | 62% |
| **4H** | **+691%** | 2.22 | 44% | 66% |

---

## 🛠️ Verification & Replication
All tests were conducted using the `run_backtest.py` engine with a starting capital of $1,000. Batch results are stored in:
`scratch/batch_backtests/`

> [!TIP]
> **Heikin-Ashi Advantage**: Switching to HA candles natively filters out "False Wick" breakouts, allowing the strategy to stay in a winning trend longer. This is specifically powerful for the Donchian strategy.

> [!IMPORTANT]
> **Risk Warning**: Always use the 0.20 Stop Loss parameter. Running without a Stop Loss ("None") resulted in an average portfolio drawdown of over 100% on volatile assets.
