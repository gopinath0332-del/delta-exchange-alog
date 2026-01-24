"""Unit tests for portfolio optimization module.

Tests the PortfolioOptimizer, optimization engines, and related functionality.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from portfolio.optimizer import (
    PortfolioOptimizer,
    MeanVarianceOptimizer,
    RiskParityOptimizer,
    MaxDiversificationOptimizer,
    OptimizationConstraints
)
from portfolio.allocator import AllocationManager, ConstraintValidator, RebalancingTrigger
from portfolio.metrics import RiskMetrics, CorrelationAnalyzer


# Fixtures

@pytest.fixture
def sample_returns():
    """Generate sample returns data for testing."""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    
    returns = pd.DataFrame({
        'strategy_a': np.random.normal(0.001, 0.02, 100),
        'strategy_b': np.random.normal(0.0008, 0.015, 100),
        'strategy_c': np.random.normal(0.0012, 0.025, 100)
    }, index=dates)
    
    return returns


@pytest.fixture
def constraints():
    """Default optimization constraints."""
    return OptimizationConstraints(
        max_single_strategy=0.40,
        min_single_strategy=0.05,
        cash_reserve=0.05
    )


# PortfolioOptimizer Tests

class TestPortfolioOptimizer:
    """Tests for PortfolioOptimizer class."""
    
    def test_initialization(self, constraints):
        """Test optimizer initialization."""
        optimizer = PortfolioOptimizer(
            method='mean_variance',
            constraints=constraints
        )
        
        assert optimizer.method == 'mean_variance'
        assert optimizer.constraints == constraints
        assert optimizer.risk_free_rate == 0.02
    
    def test_mean_variance_optimization(self, sample_returns, constraints):
        """Test mean-variance optimization produces valid weights."""
        optimizer = PortfolioOptimizer(method='mean_variance', constraints=constraints)
        
        weights = optimizer.optimize(sample_returns)
        
        # Check weights sum to approximately 1 - cash_reserve
        total_weight = sum(weights.values())
        assert 0.90 <= total_weight <= 1.0
        
        # Check individual constraints
        for weight in weights.values():
            assert weight >= constraints.min_single_strategy
            assert weight <= constraints.max_single_strategy
    
    def test_risk_parity_optimization(self, sample_returns, constraints):
        """Test risk parity optimization."""
        optimizer = PortfolioOptimizer(method='risk_parity', constraints=constraints)
        
        weights = optimizer.optimize(sample_returns)
        
        # Check weights sum to approximately 1 - cash_reserve
        total_weight = sum(weights.values())
        assert 0.90 <= total_weight <= 1.0
        
        # Check all strategies have some allocation
        assert all(w > 0 for w in weights.values())
    
    def test_max_diversification_optimization(self, sample_returns, constraints):
        """Test maximum diversification optimization."""
        optimizer = PortfolioOptimizer(method='max_div', constraints=constraints)
        
        weights = optimizer.optimize(sample_returns)
        
        # Check weights are valid
        total_weight = sum(weights.values())
        assert 0.90 <= total_weight <= 1.0
    
    def test_portfolio_metrics_calculation(self, sample_returns, constraints):
        """Test portfolio metrics calculation."""
        optimizer = PortfolioOptimizer(method='mean_variance', constraints=constraints)
        weights = optimizer.optimize(sample_returns)
        
        metrics = optimizer.calculate_portfolio_metrics(weights, sample_returns)
        
        # Check all metrics are present
        assert 'annual_return' in metrics
        assert 'annual_volatility' in metrics
        assert 'sharpe_ratio' in metrics
        assert 'max_drawdown' in metrics
        
        # Check metrics are reasonable
        assert -1.0 <= metrics['annual_return'] <= 1.0
        assert metrics['annual_volatility'] >= 0
        assert metrics['max_drawdown'] <= 0  # Drawdown is negative


# Allocation Manager Tests

class TestAllocationManager:
    """Tests for AllocationManager class."""
    
    def test_initialization(self):
        """Test allocation manager initialization."""
        manager = AllocationManager(
            total_capital=10000,
            rebalancing_method='threshold',
            rebalancing_threshold=0.05
        )
        
        assert manager.total_capital == 10000
        assert manager.rebalancing_threshold == 0.05
    
    def test_capital_allocation_calculation(self):
        """Test converting weights to capital amounts."""
        manager = AllocationManager(total_capital=10000)
        
        weights = {'strategy_a': 0.40, 'strategy_b': 0.35, 'strategy_c': 0.20}
        allocation = manager.calculate_capital_allocation(weights)
        
        assert allocation['strategy_a'] == 4000
        assert allocation['strategy_b'] == 3500
        assert allocation['strategy_c'] == 2000
    
    def test_threshold_rebalancing_trigger(self):
        """Test threshold-based rebalancing detection."""
        manager = AllocationManager(
            total_capital=10000,
            rebalancing_method='threshold',
            rebalancing_threshold=0.05
        )
        
        # Set target weights
        manager.target_weights = {'strategy_a': 0.40, 'strategy_b': 0.60}
        
        # Simulate drift beyond threshold
        manager.current_weights = {'strategy_a': 0.50, 'strategy_b': 0.50}
        
        needs_rebalance, trigger, reason = manager.needs_rebalancing()
        
        assert needs_rebalance is True
        assert trigger == RebalancingTrigger.THRESHOLD
    
    def test_periodic_rebalancing_trigger(self):
        """Test periodic rebalancing detection."""
        manager = AllocationManager(
            total_capital=10000,
            rebalancing_method='periodic',
            rebalancing_frequency='weekly'
        )
        
        manager.target_weights = {'strategy_a': 0.50, 'strategy_b': 0.50}
        manager.current_weights = {'strategy_a': 0.50, 'strategy_b': 0.50}
        
        # Simulate time passing
        manager.last_rebalance_time = datetime.now() - timedelta(days=8)
        
        needs_rebalance, trigger, reason = manager.needs_rebalancing()
        
        assert needs_rebalance is True
        assert trigger == RebalancingTrigger.PERIODIC


# Constraint Validator Tests

class TestConstraintValidator:
    """Tests for ConstraintValidator class."""
    
    def test_valid_weights(self):
        """Test validation of valid weights."""
        weights = {'strategy_a': 0.40, 'strategy_b': 0.35, 'strategy_c': 0.20}
        
        is_valid, error = ConstraintValidator.validate_weights(
            weights,
            min_weight=0.05,
            max_weight=0.50
        )
        
        assert is_valid is True
        assert error is None
    
    def test_weights_sum_validation(self):
        """Test weights sum validation."""
        weights = {'strategy_a': 0.40, 'strategy_b': 0.35, 'strategy_c': 0.10}
        
        is_valid, error = ConstraintValidator.validate_weights(weights)
        
        assert is_valid is False
        assert "sum" in error.lower()
    
    def test_weight_bounds_validation(self):
        """Test individual weight bounds."""
        weights = {'strategy_a': 0.60, 'strategy_b': 0.40}
        
        is_valid, error = ConstraintValidator.validate_weights(
            weights,
            max_weight=0.50
        )
        
        assert is_valid is False
        assert "exceeds maximum" in error.lower()
    
    def test_correlation_validation(self, sample_returns):
        """Test correlation validation."""
        is_valid, error = ConstraintValidator.validate_correlation(
            sample_returns,
            max_correlation=0.80
        )
        
        # With random data, should generally pass
        assert is_valid is True
    
    def test_strategy_count_validation(self):
        """Test strategy count validation."""
        weights = {'strategy_a': 0.50, 'strategy_b': 0.50}
        
        # Test minimum violation
        is_valid, error = ConstraintValidator.validate_strategy_count(
            weights,
            min_strategies=3
        )
        
        assert is_valid is False
        assert "minimum" in error.lower()
        
        # Test maximum violation
        weights = {f'strategy_{i}': 0.125 for i in range(8)}
        
        is_valid, error = ConstraintValidator.validate_strategy_count(
            weights,
            max_strategies=5
        )
        
        assert is_valid is False
        assert "exceeds maximum" in error.lower()


# Risk Metrics Tests

class TestRiskMetrics:
    """Tests for RiskMetrics class."""
    
    def test_sharpe_ratio(self, sample_returns):
        """Test Sharpe ratio calculation."""
        returns = sample_returns['strategy_a']
        sharpe = RiskMetrics.sharpe_ratio(returns, risk_free_rate=0.02)
        
        # Sharpe should be a reasonable number
        assert -5.0 <= sharpe <= 5.0
    
    def test_sortino_ratio(self, sample_returns):
        """Test Sortino ratio calculation."""
        returns = sample_returns['strategy_a']
        sortino = RiskMetrics.sortino_ratio(returns, risk_free_rate=0.02)
        
        assert -5.0 <= sortino <= 5.0
    
    def test_max_drawdown(self, sample_returns):
        """Test maximum drawdown calculation."""
        returns = sample_returns['strategy_a']
        max_dd = RiskMetrics.max_drawdown(returns)
        
        # Drawdown should be negative or zero
        assert max_dd <= 0
        assert max_dd >= -1.0  # Can't lose more than 100%
    
    def test_win_rate(self):
        """Test win rate calculation."""
        # Create returns with known win rate
        returns = pd.Series([0.01, -0.01, 0.01, 0.01, -0.01])
        win_rate = RiskMetrics.win_rate(returns)
        
        assert win_rate == 0.6  # 3 out of 5 are positive
    
    def test_profit_factor(self):
        """Test profit factor calculation."""
        returns = pd.Series([0.02, -0.01, 0.03, -0.01])
        profit_factor = RiskMetrics.profit_factor(returns)
        
        # (0.02 + 0.03) / (0.01 + 0.01) = 2.5
        assert abs(profit_factor - 2.5) < 0.001
    
    def test_diversification_benefit(self):
        """Test diversification benefit calculation."""
        weights = np.array([0.40, 0.35, 0.25])
        volatilities = np.array([0.20, 0.15, 0.25])
        portfolio_vol = 0.12
        
        div_benefit = RiskMetrics.diversification_benefit(
            weights,
            volatilities,
            portfolio_vol
        )
        
        # Diversification benefit should be between 0 and 1
        assert 0 <= div_benefit <= 1


# Correlation Analyzer Tests

class TestCorrelationAnalyzer:
    """Tests for CorrelationAnalyzer class."""
    
    def test_correlation_matrix_calculation(self, sample_returns):
        """Test correlation matrix calculation."""
        corr_matrix = CorrelationAnalyzer.calculate_correlation_matrix(sample_returns)
        
        # Check dimensions
        assert corr_matrix.shape == (3, 3)
        
        # Check diagonal is 1.0 (strategy correlated with itself)
        assert corr_matrix.iloc[0, 0] == 1.0
        assert corr_matrix.iloc[1, 1] == 1.0
        assert corr_matrix.iloc[2, 2] == 1.0
        
        # Check symmetry
        assert corr_matrix.iloc[0, 1] == corr_matrix.iloc[1, 0]
    
    def test_find_highly_correlated_pairs(self):
        """Test finding highly correlated strategy pairs."""
        # Create correlation matrix with known high correlation
        corr_data = {
            'strategy_a': [1.0, 0.85, 0.30],
            'strategy_b': [0.85, 1.0, 0.25],
            'strategy_c': [0.30, 0.25, 1.0]
        }
        corr_matrix = pd.DataFrame(
            corr_data,
            index=['strategy_a', 'strategy_b', 'strategy_c']
        )
        
        high_corr_pairs = CorrelationAnalyzer.find_highly_correlated_pairs(
            corr_matrix,
            threshold=0.80
        )
        
        # Should find strategy_a and strategy_b
        assert len(high_corr_pairs) == 1
        assert high_corr_pairs[0][0] == 'strategy_a'
        assert high_corr_pairs[0][1] == 'strategy_b'
        assert high_corr_pairs[0][2] == 0.85


# Integration Tests

class TestPortfolioIntegration:
    """Integration tests for portfolio components."""
    
    def test_full_optimization_workflow(self, sample_returns, constraints):
        """Test complete optimization workflow."""
        # Initialize optimizer
        optimizer = PortfolioOptimizer(
            method='mean_variance',
            constraints=constraints
        )
        
        # Run optimization
        weights = optimizer.optimize(sample_returns)
        
        # Validate weights
        is_valid, error = ConstraintValidator.validate_weights(
            weights,
            min_weight=constraints.min_single_strategy,
            max_weight=constraints.max_single_strategy
        )
        
        assert is_valid, f"Invalid weights: {error}"
        
        # Calculate metrics
        metrics = optimizer.calculate_portfolio_metrics(weights, sample_returns)
        
        assert metrics['sharpe_ratio'] is not None
        assert metrics['annual_return'] is not None
    
    def test_allocation_and_rebalancing_workflow(self):
        """Test allocation calculation and rebalancing."""
        # Initialize allocator
        allocator = AllocationManager(
            total_capital=10000,
            rebalancing_method='threshold',
            rebalancing_threshold=0.05
        )
        
        # Set initial allocation
        initial_weights = {'strategy_a': 0.40, 'strategy_b': 0.35, 'strategy_c': 0.20}
        allocator.set_target_allocation(initial_weights)
        
        # Calculate capital
        capital = allocator.calculate_capital_allocation(initial_weights)
        
        assert sum(capital.values()) == 9500  # 95% of 10000 (5% cash reserve in constraints)
        
        # Simulate drift
        current_values = {'strategy_a': 5000, 'strategy_b': 3000, 'strategy_c': 1500}
        allocator.update_current_weights(current_values)
        
        # Check if rebalancing needed
        needs_rebalance, trigger, reason = allocator.needs_rebalancing()
        
        if needs_rebalance:
            # Calculate rebalancing trades
            trades = allocator.calculate_rebalancing_trades(current_values)
            assert len(trades) == len(current_values)
