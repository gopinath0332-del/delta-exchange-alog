"""Portfolio allocation and rebalancing management.

This module handles capital allocation, rebalancing triggers, and constraint validation
for the portfolio optimization system.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum

from core.logger import get_logger

logger = get_logger(__name__)


class RebalancingTrigger(Enum):
    """Types of rebalancing triggers."""
    PERIODIC = "periodic"
    THRESHOLD = "threshold"
    PERFORMANCE = "performance"
    MANUAL = "manual"


class AllocationManager:
    """Manages portfolio allocation and rebalancing.
    
    This class handles:
    - Converting optimal weights to capital allocations
    - Detecting when rebalancing is needed
    - Executing rebalancing trades
    - Validating portfolio constraints
    
    Attributes:
        total_capital: Total capital available for allocation
        current_weights: Current portfolio weights
        target_weights: Target portfolio weights from optimization
    """
    
    def __init__(
        self,
        total_capital: float,
        rebalancing_method: str = 'threshold',
        rebalancing_threshold: float = 0.05,
        rebalancing_frequency: str = 'weekly'
    ):
        """Initialize allocation manager.
        
        Args:
            total_capital: Total capital available for portfolio
            rebalancing_method: 'periodic', 'threshold', or 'performance_based'
            rebalancing_threshold: Drift threshold for rebalancing (e.g., 0.05 = 5%)
            rebalancing_frequency: 'daily', 'weekly', or 'monthly' for periodic rebalancing
        """
        self.total_capital = total_capital
        self.rebalancing_method = rebalancing_method
        self.rebalancing_threshold = rebalancing_threshold
        self.rebalancing_frequency = rebalancing_frequency
        
        self.current_weights: Dict[str, float] = {}
        self.target_weights: Dict[str, float] = {}
        self.last_rebalance_time: Optional[datetime] = None
        
        logger.info(
            "Allocation manager initialized",
            capital=total_capital,
            method=rebalancing_method,
            threshold=rebalancing_threshold
        )
    
    def set_target_allocation(self, weights: Dict[str, float]) -> None:
        """Set target allocation weights.
        
        Args:
            weights: Dictionary mapping strategy names to target weights
        """
        self.target_weights = weights
        logger.info("Target allocation set", weights=weights)
    
    def calculate_capital_allocation(
        self,
        weights: Dict[str, float]
    ) -> Dict[str, float]:
        """Convert weights to capital allocations.
        
        Args:
            weights: Dictionary mapping strategy names to weights (0-1)
        
        Returns:
            Dictionary mapping strategy names to capital amounts
        """
        allocation = {
            strategy: weight * self.total_capital
            for strategy, weight in weights.items()
        }
        
        logger.info(
            "Capital allocation calculated",
            total=sum(allocation.values()),
            allocation=allocation
        )
        
        return allocation
    
    def update_current_weights(
        self,
        strategy_values: Dict[str, float]
    ) -> Dict[str, float]:
        """Update current portfolio weights based on strategy values.
        
        Args:
            strategy_values: Current market value of each strategy position
        
        Returns:
            Updated current weights
        """
        total_value = sum(strategy_values.values())
        
        if total_value > 0:
            self.current_weights = {
                strategy: value / total_value
                for strategy, value in strategy_values.items()
            }
        else:
            self.current_weights = {strategy: 0.0 for strategy in strategy_values.keys()}
        
        return self.current_weights
    
    def needs_rebalancing(
        self,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, Optional[RebalancingTrigger], Optional[str]]:
        """Check if portfolio needs rebalancing.
        
        Args:
            current_time: Current datetime (uses now() if None)
        
        Returns:
            Tuple of (needs_rebalancing, trigger_type, reason)
        """
        if not self.target_weights or not self.current_weights:
            return False, None, None
        
        current_time = current_time or datetime.now()
        
        # Check threshold-based rebalancing
        if self.rebalancing_method in ['threshold', 'both']:
            max_drift = self._calculate_max_drift()
            if max_drift > self.rebalancing_threshold:
                reason = f"Drift {max_drift:.2%} exceeds threshold {self.rebalancing_threshold:.2%}"
                logger.info("Rebalancing needed", reason=reason, trigger="threshold")
                return True, RebalancingTrigger.THRESHOLD, reason
        
        # Check periodic rebalancing
        if self.rebalancing_method in ['periodic', 'both']:
            if self._is_rebalance_period_elapsed(current_time):
                reason = f"Periodic rebalancing due ({self.rebalancing_frequency})"
                logger.info("Rebalancing needed", reason=reason, trigger="periodic")
                return True, RebalancingTrigger.PERIODIC, reason
        
        return False, None, None
    
    def _calculate_max_drift(self) -> float:
        """Calculate maximum drift from target weights.
        
        Returns:
            Maximum absolute drift across all strategies
        """
        drifts = []
        for strategy in self.target_weights.keys():
            current = self.current_weights.get(strategy, 0.0)
            target = self.target_weights.get(strategy, 0.0)
            drift = abs(current - target)
            drifts.append(drift)
        
        return max(drifts) if drifts else 0.0
    
    def _is_rebalance_period_elapsed(self, current_time: datetime) -> bool:
        """Check if rebalancing period has elapsed.
        
        Args:
            current_time: Current datetime
        
        Returns:
            True if rebalancing period has elapsed
        """
        if self.last_rebalance_time is None:
            return True
        
        elapsed = current_time - self.last_rebalance_time
        
        if self.rebalancing_frequency == 'daily':
            return elapsed >= timedelta(days=1)
        elif self.rebalancing_frequency == 'weekly':
            return elapsed >= timedelta(weeks=1)
        elif self.rebalancing_frequency == 'monthly':
            return elapsed >= timedelta(days=30)
        
        return False
    
    def calculate_rebalancing_trades(
        self,
        current_values: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate trades needed to rebalance portfolio.
        
        Args:
            current_values: Current market value of each strategy
        
        Returns:
            Dictionary mapping strategy names to trade amounts (positive = buy, negative = sell)
        """
        total_value = sum(current_values.values())
        
        trades = {}
        for strategy, target_weight in self.target_weights.items():
            current_value = current_values.get(strategy, 0.0)
            target_value = target_weight * total_value
            trade_amount = target_value - current_value
            trades[strategy] = trade_amount
        
        logger.info(
            "Rebalancing trades calculated",
            trades=trades,
            total_value=total_value
        )
        
        return trades
    
    def execute_rebalance(self) -> None:
        """Mark rebalancing as executed."""
        self.last_rebalance_time = datetime.now()
        logger.info("Rebalancing executed", timestamp=self.last_rebalance_time)


class ConstraintValidator:
    """Validates portfolio constraints.
    
    Ensures allocations meet portfolio requirements like:
    - Min/max weights per strategy
    - Maximum correlation between strategies
    - Minimum number of strategies
    """
    
    @staticmethod
    def validate_weights(
        weights: Dict[str, float],
        min_weight: float = 0.0,
        max_weight: float = 1.0
    ) -> Tuple[bool, Optional[str]]:
        """Validate portfolio weights.
        
        Args:
            weights: Strategy weights to validate
            min_weight: Minimum allowed weight per strategy
            max_weight: Maximum allowed weight per strategy
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check sum to 1
        total = sum(weights.values())
        if not (0.99 <= total <= 1.01):  # Allow small floating point error
            return False, f"Weights sum to {total:.4f}, should be ~1.0"
        
        # Check individual weights
        for strategy, weight in weights.items():
            if weight < min_weight:
                return False, f"{strategy} weight {weight:.4f} below minimum {min_weight}"
            if weight > max_weight:
                return False, f"{strategy} weight {weight:.4f} exceeds maximum {max_weight}"
        
        return True, None
    
    @staticmethod
    def validate_correlation(
        returns: pd.DataFrame,
        max_correlation: float = 0.80
    ) -> Tuple[bool, Optional[str]]:
        """Validate that strategies aren't too highly correlated.
        
        Args:
            returns: DataFrame with strategy returns
            max_correlation: Maximum allowed correlation
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        corr_matrix = returns.corr()
        
        # Check off-diagonal elements
        for i in range(len(corr_matrix)):
            for j in range(i + 1, len(corr_matrix)):
                corr = abs(corr_matrix.iloc[i, j])
                if corr > max_correlation:
                    strategy_a = corr_matrix.index[i]
                    strategy_b = corr_matrix.columns[j]
                    return False, f"Correlation between {strategy_a} and {strategy_b} is {corr:.3f}, exceeds {max_correlation}"
        
        return True, None
    
    @staticmethod
    def validate_strategy_count(
        weights: Dict[str, float],
        min_strategies: int = 1,
        max_strategies: int = 10
    ) -> Tuple[bool, Optional[str]]:
        """Validate number of strategies in portfolio.
        
        Args:
            weights: Strategy weights
            min_strategies: Minimum number of strategies
            max_strategies: Maximum number of strategies
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Count strategies with non-zero allocation
        active_strategies = sum(1 for w in weights.values() if w > 0.001)
        
        if active_strategies < min_strategies:
            return False, f"Only {active_strategies} active strategies, minimum is {min_strategies}"
        
        if active_strategies > max_strategies:
            return False, f"{active_strategies} active strategies exceeds maximum of {max_strategies}"
        
        return True, None
