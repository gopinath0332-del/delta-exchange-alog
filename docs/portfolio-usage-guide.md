# Portfolio Optimization Usage Guide

## Overview

This guide explains how to use the portfolio optimization and multi-strategy allocation features to run multiple trading strategies simultaneously with optimal capital allocation.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Configuration](#configuration)
3. [Running Portfolio Mode](#running-portfolio-mode)
4. [Optimization Methods](#optimization-methods)
5. [Rebalancing](#rebalancing)
6. [Performance Monitoring](#performance-monitoring)
7. [Advanced Topics](#advanced-topics)
8. [Troubleshooting](#troubleshooting)

## Getting Started

### Installation

1. Install portfolio optimization dependencies:

```bash
pip install scipy cvxpy cvxopt
```

2. Copy the portfolio configuration template:

```bash
cp config/portfolio_optimization.yaml.example config/portfolio_optimization.yaml
```

3. Configure environment variables in `.env`:

```bash
PORTFOLIO_MODE_ENABLED=true
PORTFOLIO_TOTAL_CAPITAL=10000
PORTFOLIO_OPTIMIZATION_METHOD=mean_variance
```

## Configuration

### Portfolio Settings

Edit `config/portfolio_optimization.yaml`:

```yaml
portfolio:
  enabled: true
  total_capital: 10000
  optimization_method: mean_variance # mean_variance, risk_parity, max_div
  risk_tolerance: moderate # conservative, moderate, aggressive
```

### Constraints

Define portfolio constraints to manage risk:

```yaml
constraints:
  max_single_strategy: 0.40 # Max 40% in any strategy
  min_single_strategy: 0.05 # Min 5% per strategy
  max_correlation: 0.80 # Avoid highly correlated strategies
  min_strategies: 3 # Minimum diversification
  max_strategies: 8 # Maximum concurrent strategies
  cash_reserve: 0.05 # Keep 5% in cash
```

### Strategy Pool

Select which strategies to include in your portfolio:

```yaml
strategies:
  - name: double_dip_rsi
    symbol: BTCUSD
    timeframe: 1h
    candle_type: heikin-ashi
    enabled: true

  - name: rsi_200_ema
    symbol: ETHUSD
    timeframe: 3h
    candle_type: heikin-ashi
    enabled: true

  - name: macd_psar_100ema
    symbol: XRPUSD
    timeframe: 1h
    candle_type: heikin-ashi
    enabled: true
```

## Running Portfolio Mode

### Basic Usage

Run portfolio in paper trading mode:

```bash
python run_portfolio.py run --mode paper
```

Run portfolio in live mode:

```bash
python run_portfolio.py run --mode live
```

### Optimization Only

See recommended allocation without executing:

```bash
python run_portfolio.py optimize
```

Example output:

```
==============================================================
PORTFOLIO OPTIMIZATION RESULTS
==============================================================

Optimization Method: mean_variance
Total Capital: $10,000.00
Cash Reserve: 5.0%

Optimal Allocation:
--------------------------------------------------------------
  rsi_200_ema         :  35.0%  ($ 3,500.00)
  double_dip_rsi      :  30.0%  ($ 3,000.00)
  macd_psar_100ema    :  20.0%  ($ 2,000.00)
  cci_ema             :  10.0%  ($ 1,000.00)
--------------------------------------------------------------
  Total Allocated     :  95.0%  ($ 9,500.00)
  Cash Reserve        :   5.0%  ($   500.00)
==============================================================
```

## Optimization Methods

### 1. Mean-Variance Optimization (Default)

**What it does**: Maximizes risk-adjusted returns (Sharpe ratio)

**Best for**: Balancing returns and volatility

**Configuration**:

```yaml
optimization_method: mean_variance
optimization:
  mean_variance:
    risk_aversion: 0.5 # Higher = more conservative
```

**Example**:

```bash
python run_portfolio.py run --method mean_variance --mode paper
```

### 2. Risk Parity

**What it does**: Allocates capital so each strategy contributes equally to portfolio risk

**Best for**: Maximum diversification, reducing over-concentration in volatile strategies

**Configuration**:

```yaml
optimization_method: risk_parity
optimization:
  risk_parity:
    volatility_lookback: 60 # Days for volatility calculation
```

**Example**:

```bash
python run_portfolio.py run --method risk_parity --mode paper
```

**Result**: Lower-volatility strategies get higher allocation

### 3. Maximum Diversification

**What it does**: Maximizes the diversification ratio, favoring low-correlated strategies

**Best for**: Portfolios with strategies that have low correlation

**Configuration**:

```yaml
optimization_method: max_div
optimization:
  max_div:
    correlation_lookback: 90 # Days for correlation calculation
```

**Example**:

```bash
python run_portfolio.py run --method max_div --mode paper
```

## Rebalancing

### Automatic Rebalancing

Configure rebalancing triggers in `portfolio_optimization.yaml`:

```yaml
rebalancing:
  frequency: weekly # daily, weekly, monthly
  threshold: 0.05 # Rebalance if drift > 5%
  method: threshold # periodic, threshold, both
```

**Threshold Rebalancing**: Triggers when any strategy drifts > 5% from target weight

```yaml
rebalancing:
  method: threshold
  threshold: 0.05
```

**Periodic Rebalancing**: Rebalances on schedule regardless of drift

```yaml
rebalancing:
  method: periodic
  frequency: weekly
```

**Combined**: Uses both triggers

```yaml
rebalancing:
  method: both
  threshold: 0.05
  frequency: weekly
```

### Manual Rebalancing

Trigger rebalancing manually:

```bash
python run_portfolio.py rebalance
```

This will:

1. Calculate new optimal allocation
2. Show recommended trades
3. Ask for confirmation before executing

## Performance Monitoring

### View Current Allocation

```bash
python run_portfolio.py show-allocation
```

### View Strategy Performance

All strategies:

```bash
python run_portfolio.py performance
```

Specific strategy:

```bash
python run_portfolio.py performance --strategy double_dip_rsi --days 60
```

Example output:

```
Strategy: double_dip_rsi
Lookback: 60 days
--------------------------------------------------------------
  Annual Return:     18.50%
  Volatility:        22.30%
  Sharpe Ratio:       0.74
  Sortino Ratio:      1.02
  Max Drawdown:     -12.40%
  Win Rate:          58.00%
  Profit Factor:      1.85
  Calmar Ratio:       1.49
```

### Live Dashboard

Run live portfolio dashboard (coming soon):

```bash
python run_portfolio.py dashboard
```

## Advanced Topics

### Risk Management

Configure portfolio-level risk controls:

```yaml
risk_management:
  portfolio_max_drawdown: -0.20 # Stop all trading at -20% drawdown
  strategy_max_drawdown: -0.15 # Reduce allocation at -15% strategy DD
  min_sharpe_ratio: 0.5 # Remove strategies with Sharpe < 0.5
  lookback_period: 30 # Days for evaluation
```

### Performance-Based Rebalancing

Automatically adjust allocations based on performance:

```yaml
rebalancing:
  method: performance_based

risk_management:
  strategy_max_drawdown: -0.15 # Reduce allocation if strategy DD > 15%
  min_sharpe_ratio: 0.5 # Remove low-performing strategies
```

### Backtesting Portfolio

Compare portfolio performance vs individual strategies:

```bash
python run_portfolio.py backtest --start-date 2024-01-01 --end-date 2024-12-31
```

This will show:

- Portfolio cumulative return
- Individual strategy returns
- Sharpe ratio comparison
- Diversification benefit
- Maximum drawdown comparison

## Troubleshooting

### Issue: Optimization fails with "Insufficient strategy history"

**Solution**: Strategies need at least 30 days of performance history. Run strategies individually first to build history.

```yaml
performance:
  min_history_days: 30 # Minimum history required
```

### Issue: "Correlation too high" error

**Solution**: Some strategies are too highly correlated. Disable one of the correlated strategies:

```yaml
strategies:
  - name: rsi_50_ema
    enabled: false # Disable if correlated with another XRP strategy
```

Or increase correlation threshold:

```yaml
constraints:
  max_correlation: 0.90 # Allow higher correlation
```

### Issue: All capital allocated to one strategy

**Solution**: Constraints might be too loose. Tighten max allocation:

```yaml
constraints:
  max_single_strategy: 0.35 # Reduce from 0.40 to 0.35
  min_single_strategy: 0.10 # Increase from 0.05 to 0.10
  min_strategies: 4 # Require more strategies
```

### Issue: Rebalancing too frequent

**Solution**: Increase threshold or use periodic rebalancing:

```yaml
rebalancing:
  threshold: 0.10 # Increase from 0.05 to 0.10
  frequency: monthly # Change from weekly to monthly
```

## Best Practices

1. **Start with Paper Trading**: Always test portfolio mode in paper trading before live

2. **Build Performance History**: Run strategies individually for at least 30 days before portfolio optimization

3. **Diversify Across Assets**: Use strategies on different symbols (BTC, ETH, XRP) for better diversification

4. **Monitor Correlations**: Regularly check strategy correlations. Avoid combining highly correlated strategies

5. **Conservative Constraints**: Start with conservative constraints and adjust based on results:
   - `max_single_strategy: 0.30` (30% max per strategy)
   - `min_strategies: 4` (require good diversification)
   - `cash_reserve: 0.10` (10% cash buffer)

6. **Regular Rebalancing**: Weekly threshold-based rebalancing with 5% drift threshold works well

7. **Risk Management**: Always set portfolio-level risk limits:
   - `portfolio_max_drawdown: -0.15` (stop at -15%)
   - `strategy_max_drawdown: -0.10` (reduce allocation at -10%)

## Next Steps

- Review [portfolio-optimization.md](portfolio-optimization.md) for theory and mathematics
- Check [implementation_plan.md](implementation_plan.md) for technical details
- See [README.md](../README.md) for general platform documentation

## Support

For issues or questions:

- Check logs in `logs/trading.log`
- Review database in `data/portfolio_performance.db`
- See Discord notifications for portfolio events
