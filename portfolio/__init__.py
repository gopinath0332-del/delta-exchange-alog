"""Portfolio Optimization Module.

This module provides portfolio optimization and multi-strategy allocation capabilities,
enabling running multiple trading strategies simultaneously with optimal capital allocation
for risk-adjusted returns.
"""

from portfolio.optimizer import PortfolioOptimizer
from portfolio.allocator import AllocationManager
from portfolio.metrics import PerformanceTracker, RiskMetrics

__all__ = [
    'PortfolioOptimizer',
    'AllocationManager',
    'PerformanceTracker',
    'RiskMetrics',
]
