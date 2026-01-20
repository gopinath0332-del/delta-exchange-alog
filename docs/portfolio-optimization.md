# Portfolio Optimization and Multi-Strategy Allocation

## Overview

This document outlines the planned portfolio optimization and multi-strategy allocation feature for the Delta Exchange trading platform. This capability will enable running multiple trading strategies simultaneously with optimal capital allocation for risk-adjusted returns.

## Current State

The platform currently supports:

- Running **one strategy at a time** on a single asset
- 100% capital allocation to the active strategy
- Manual strategy selection and switching

**Limitations:**

- High concentration risk (single strategy, single asset)
- No diversification benefits
- Full exposure to individual strategy performance
- Manual rebalancing required

## Future Vision: Multi-Strategy Portfolio

### Concurrent Strategy Execution

Run multiple strategies simultaneously across different assets and timeframes:

```
Portfolio Example:
├─ Strategy 1: Double-Dip RSI (BTCUSD, 1h)     → 30% allocation
├─ Strategy 2: RSI-200-EMA (ETHUSD, 3h)        → 25% allocation
├─ Strategy 3: MACD-PSAR (XRPUSD, 1h)          → 20% allocation
├─ Strategy 4: CCI-EMA (BTCUSD, 4h)            → 15% allocation
├─ Strategy 5: RSI-50-EMA (XRPUSD alt, 1h)    → 5% allocation
└─ Cash Reserve                                 → 5%
```

### Benefits

1. **Diversification**: Spread risk across multiple strategies and assets
2. **Reduced Volatility**: Uncorrelated strategies smooth overall returns
3. **Improved Sharpe Ratio**: Better risk-adjusted returns
4. **Strategy Redundancy**: Protection from individual strategy failure
5. **Market Condition Adaptation**: Different strategies perform better in different market regimes

## Portfolio Optimization Methods

### 1. Mean-Variance Optimization (Modern Portfolio Theory)

**Concept**: Maximize expected return for a given level of risk, or minimize risk for a target return.

**Mathematics**:

```
Objective: Maximize Sharpe Ratio = (Rp - Rf) / σp

Where:
- Rp = Expected portfolio return
- Rf = Risk-free rate
- σp = Portfolio standard deviation

Subject to:
- Σ wi = 1 (weights sum to 100%)
- 0 ≤ wi ≤ wmax (position limits)
- wi ≥ 0 (no shorting)
```

**Process**:

1. Calculate expected returns for each strategy (historical mean)
2. Calculate covariance matrix (how strategies move together)
3. Solve quadratic optimization problem
4. Generate efficient frontier (optimal portfolios at each risk level)

**Example Output**:

```
Conservative Portfolio (σ = 10%):
  Double-Dip RSI: 20%
  RSI-200-EMA:    35%
  MACD-PSAR:      25%
  CCI-EMA:        15%
  Cash:           5%
  Expected Return: 18% annually

Aggressive Portfolio (σ = 20%):
  Double-Dip RSI: 40%
  RSI-200-EMA:    25%
  MACD-PSAR:      20%
  CCI-EMA:        10%
  Cash:           5%
  Expected Return: 32% annually
```

### 2. Risk Parity

**Concept**: Allocate capital so each strategy contributes **equally to portfolio risk**, not capital.

**Why**: High-return strategies often have high volatility. Risk parity prevents over-concentration in volatile strategies.

**Formula**:

```
Risk Contribution of Strategy i = wi × σi × ρi,p

Goal: Equal risk contribution from each strategy
```

**Example**:

```
Strategy          Volatility    Capital Weight    Risk Contribution
Double-Dip RSI    25%          20%               Equal (25%)
RSI-200-EMA       15%          33%               Equal (25%)
MACD-PSAR         10%          50%               Equal (25%)
CCI-EMA           20%          25%               Equal (25%)
```

### 3. Black-Litterman Model

**Concept**: Combine market equilibrium returns with investor views (strategy performance beliefs).

**Advantages**:

- Reduces estimation error
- Incorporates both historical data and forward-looking views
- More stable allocations (less turnover)

**Use Case**:

```
Historical Data says: RSI-200-EMA returns 25% annually
Your View: Upcoming ETH upgrade will boost performance to 35%
Black-Litterman: Blends both → Optimal allocation increases to RSI-200-EMA
```

### 4. Maximum Diversification

**Concept**: Maximize the diversification ratio.

**Formula**:

```
Diversification Ratio = (Σ wi × σi) / σp

Goal: Maximize DR (highest diversification benefit)
```

**Result**: Favors strategies with low correlation to others.

## Correlation Analysis

### Importance

Correlation measures how strategies move together:

- **ρ = +1.0**: Perfect positive correlation (move together)
- **ρ = 0.0**: No correlation (independent)
- **ρ = -1.0**: Perfect negative correlation (move oppositely)

**Ideal Portfolio**: Mix of low or negatively correlated strategies.

### Example Correlation Matrix

```
                 Double-Dip  RSI-200  MACD-PSAR  CCI-EMA
Double-Dip RSI      1.00     0.65      0.45      0.75
RSI-200-EMA         0.65     1.00      0.30      0.50
MACD-PSAR           0.45     0.30      1.00      0.40
CCI-EMA             0.75     0.50      0.40      1.00
```

**Interpretation**:

- Double-Dip RSI and CCI-EMA are highly correlated (0.75) → Don't overweight both
- RSI-200-EMA and MACD-PSAR are weakly correlated (0.30) → Good diversification pair

### Diversification Benefit

**Without Diversification**:

```
100% in Double-Dip RSI
Expected Return: 30%
Volatility: 25%
Sharpe Ratio: 1.2
```

**With Diversification**:

```
Mix of 4 strategies (optimized)
Expected Return: 28%
Volatility: 15%  ← 40% lower!
Sharpe Ratio: 1.87 ← 56% higher!
```

## Dynamic Rebalancing

### Trigger Mechanisms

**1. Periodic Rebalancing**

- Daily/Weekly/Monthly schedule
- Restore to target allocations
- Prevents drift from optimal weights

**2. Threshold Rebalancing**

```
If allocation drifts > 5% from target:
  Target: Double-Dip RSI 30%
  Current: 37% (due to strong performance)
  Action: Reduce to 30%, reallocate excess
```

**3. Performance-Based**

```
If strategy drawdown > -15%:
  Action: Reduce allocation by 50%
  Reallocate to better-performing strategies

If strategy Sharpe ratio < 0.5 over 30 days:
  Action: Remove from portfolio temporarily
```

**4. Market Condition**

```
High Volatility Regime (VIX > 30):
  Action: Reduce overall leverage
  Increase cash allocation
  Favor low-volatility strategies

Low Volatility Regime (VIX < 15):
  Action: Increase allocation to aggressive strategies
  Reduce cash reserve
```

## Risk Metrics

### Strategy-Level Metrics

**1. Sharpe Ratio**

```
Sharpe = (Return - Risk-Free Rate) / Volatility

Interpretation:
> 3.0 = Excellent
> 2.0 = Very Good
> 1.0 = Good
< 0.5 = Poor
```

**2. Sortino Ratio**

```
Sortino = (Return - Risk-Free Rate) / Downside Deviation

Better than Sharpe: Only penalizes downside volatility
```

**3. Maximum Drawdown**

```
Max DD = (Peak Value - Trough Value) / Peak Value

Example:
Peak: $10,000
Trough: $7,500
Max DD: -25%
```

**4. Win Rate & Profit Factor**

```
Win Rate = Winning Trades / Total Trades
Profit Factor = Gross Profit / Gross Loss

Target: Win Rate > 50%, Profit Factor > 1.5
```

### Portfolio-Level Metrics

**1. Total Portfolio Return**

```
Rp = Σ (wi × Ri)

Example:
30% × 25% + 25% × 20% + 20% × 15% + 25% × 10%
= 7.5% + 5% + 3% + 2.5% = 18% return
```

**2. Portfolio Volatility**

```
σp = √(wT × Σ × w)

Where Σ = Covariance matrix
```

**3. Portfolio Sharpe Ratio**

```
Sharpe_p = Rp / σp
```

**4. Diversification Benefit**

```
DB = 1 - (σp / Σ(wi × σi))

Higher DB = Better diversification
```

## Implementation Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                   Portfolio Manager                          │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Optimization Engine                                │     │
│  │  - Mean-Variance Optimizer                          │     │
│  │  - Risk Parity Calculator                           │     │
│  │  - Correlation Analyzer                             │     │
│  └────────────────────────────────────────────────────┘     │
│                                                               │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Allocation Manager                                 │     │
│  │  - Weight Calculator                                │     │
│  │  - Rebalancing Logic                                │     │
│  │  - Constraint Validator                             │     │
│  └────────────────────────────────────────────────────┘     │
│                                                               │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Performance Tracker                                │     │
│  │  - Strategy Returns Database                        │     │
│  │  - Risk Metrics Calculator                          │     │
│  │  - Correlation Matrix Updater                       │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │      Strategy Execution Engine           │
        │  ┌──────────┐  ┌──────────┐            │
        │  │Strategy 1│  │Strategy 2│  ...       │
        │  │(30%)     │  │(25%)     │            │
        │  └──────────┘  └──────────┘            │
        └─────────────────────────────────────────┘
```

### Database Schema

```sql
-- Strategy Performance History
CREATE TABLE strategy_performance (
    id INTEGER PRIMARY KEY,
    strategy_name TEXT,
    timestamp DATETIME,
    return_pct REAL,
    volatility REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    win_rate REAL,
    profit_factor REAL
);

-- Portfolio Allocations
CREATE TABLE portfolio_allocations (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    strategy_name TEXT,
    weight REAL,
    capital_allocated REAL,
    optimization_method TEXT
);

-- Correlation Matrix
CREATE TABLE correlation_matrix (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    strategy_a TEXT,
    strategy_b TEXT,
    correlation REAL
);
```

### Optimization Algorithm Pseudocode

```python
def optimize_portfolio(strategies, method='mean_variance', constraints=None):
    """
    Optimize portfolio allocation across strategies.

    Args:
        strategies: List of Strategy objects with historical performance
        method: 'mean_variance', 'risk_parity', 'black_litterman', 'max_div'
        constraints: Dict with min/max weights, correlation limits, etc.

    Returns:
        Dictionary of optimal weights {strategy_name: weight}
    """
    # 1. Calculate expected returns
    returns = calculate_expected_returns(strategies)

    # 2. Calculate covariance matrix
    cov_matrix = calculate_covariance(strategies)

    # 3. Run optimization
    if method == 'mean_variance':
        weights = mean_variance_optimization(returns, cov_matrix, constraints)
    elif method == 'risk_parity':
        weights = risk_parity_optimization(cov_matrix, constraints)
    elif method == 'black_litterman':
        weights = black_litterman_optimization(returns, cov_matrix, views, constraints)
    elif method == 'max_div':
        weights = max_diversification_optimization(cov_matrix, constraints)

    # 4. Validate constraints
    validate_constraints(weights, constraints)

    # 5. Return optimal allocation
    return weights
```

## Configuration Example

```yaml
# config/portfolio_optimization.yaml

portfolio:
  total_capital: 10000
  optimization_method: mean_variance # Options: mean_variance, risk_parity, black_litterman, max_div
  risk_tolerance: moderate # Options: conservative, moderate, aggressive

  constraints:
    max_single_strategy: 0.40 # Max 40% in any strategy
    min_single_strategy: 0.05 # Min 5% in any strategy
    max_correlation: 0.80 # Don't allow strategies with correlation > 0.80
    min_strategies: 3 # Require at least 3 strategies
    max_strategies: 8 # Don't exceed 8 strategies
    cash_reserve: 0.05 # Keep 5% in cash

  rebalancing:
    frequency: weekly # Options: daily, weekly, monthly
    threshold: 0.05 # Rebalance if drift > 5%
    method: threshold # Options: periodic, threshold, performance_based

  risk_management:
    portfolio_max_drawdown: -20% # Stop all trading if portfolio DD > -20%
    strategy_max_drawdown: -15% # Reduce allocation if strategy DD > -15%
    min_sharpe_ratio: 0.5 # Remove strategies with Sharpe < 0.5
    lookback_period: 30 # Days for performance evaluation

strategies:
  - name: double_dip_rsi
    symbol: BTCUSD
    timeframe: 1h
    enabled: true

  - name: rsi_200_ema
    symbol: ETHUSD
    timeframe: 3h
    enabled: true

  - name: macd_psar_100ema
    symbol: XRPUSD
    timeframe: 1h
    enabled: true

  - name: cci_ema
    symbol: BTCUSD
    timeframe: 4h
    enabled: true

  - name: rsi_50_ema
    symbol: XRPUSD
    timeframe: 1h
    enabled: false
```

## Usage Examples

### Basic Portfolio Setup

```python
from portfolio.optimizer import PortfolioOptimizer
from strategies import DoubleDipRSI, RSI200EMA, MACDPSAR

# Initialize strategies
strategies = [
    DoubleDipRSI(symbol='BTCUSD'),
    RSI200EMA(symbol='ETHUSD'),
    MACDPSAR(symbol='XRPUSD')
]

# Create optimizer
optimizer = PortfolioOptimizer(
    strategies=strategies,
    total_capital=10000,
    method='mean_variance'
)

# Get optimal allocation
allocation = optimizer.optimize()
print(allocation)
# Output: {'DoubleDipRSI': 0.35, 'RSI200EMA': 0.40, 'MACDPSAR': 0.25}
```

### Rebalancing

```python
# Check if rebalancing needed
if optimizer.needs_rebalancing(threshold=0.05):
    new_allocation = optimizer.rebalance()
    executor.execute_rebalancing(new_allocation)
```

### Performance Dashboard

```python
# Get portfolio metrics
metrics = optimizer.get_portfolio_metrics()
print(f"Portfolio Return: {metrics['return']:.2%}")
print(f"Portfolio Volatility: {metrics['volatility']:.2%}")
print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")

# Get diversification benefit
div_benefit = optimizer.calculate_diversification_benefit()
print(f"Diversification Benefit: {div_benefit:.2%}")
```

## Benefits vs. Single Strategy

### Risk Comparison

**Single Strategy (Double-Dip RSI 100%)**:

- Expected Return: 30%
- Volatility: 25%
- Sharpe Ratio: 1.2
- Max Drawdown: -35%
- **Risk**: One bad month = portfolio wipeout

**Optimized Portfolio (4 strategies)**:

- Expected Return: 28% (slightly lower)
- Volatility: 15% (**40% lower**)
- Sharpe Ratio: 1.87 (**56% higher**)
- Max Drawdown: -18% (**49% lower**)
- **Risk**: Diversified, smoother equity curve

### Real-World Example

```
Month 1:
Single: Double-Dip -15% → Portfolio: -15%
Multi:  Double-Dip -15% (30%) + RSI200 +10% (40%) + MACD +5% (30%)
        = -4.5% + 4% + 1.5% = +1% 📈

Month 2:
Single: Double-Dip +25% → Portfolio: +25%
Multi:  Double-Dip +25% (30%) + RSI200 +8% (40%) + MACD -3% (30%)
        = 7.5% + 3.2% - 0.9% = +9.8%

Result: Multi-strategy delivers more consistent returns with lower volatility
```

## Future Enhancements

1. **Machine Learning Allocation**
   - Use ML models to predict optimal weights
   - Adaptive allocation based on market regime detection
2. **Monte Carlo Simulation**
   - Stress test portfolio under various scenarios
   - Calculate Value at Risk (VaR) and Conditional VaR
3. **Walk-Forward Optimization**
   - Rolling window optimization to prevent overfitting
   - Out-of-sample validation
4. **Multi-Asset Class Support**
   - Extend beyond crypto (if exchange supports)
   - Cross-asset correlation benefits

5. **Real-Time Portfolio Dashboard**
   - Live allocation visualization
   - Strategy contribution breakdown
   - Risk metrics monitoring

## References

- Markowitz, H. (1952). "Portfolio Selection". _Journal of Finance_
- Sharpe, W. (1964). "Capital Asset Prices: A Theory of Market Equilibrium"
- Black, F. & Litterman, R. (1992). "Global Portfolio Optimization"
- Maillard, S. et al. (2010). "The Properties of Equally Weighted Risk Contribution Portfolios"

---

**Status**: Planned Feature  
**Priority**: High  
**Complexity**: Medium-High  
**Dependencies**: Historical performance tracking, correlation analysis, optimization libraries (scipy, cvxpy)
