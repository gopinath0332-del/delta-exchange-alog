"""Portfolio optimization engines implementing various allocation methods.

This module provides multiple portfolio optimization strategies:
- Mean-Variance Optimization (Modern Portfolio Theory)
- Risk Parity (Equal Risk Contribution)
- Maximum Diversification
- Black-Litterman (future enhancement)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from scipy.optimize import minimize
import cvxpy as cp
from dataclasses import dataclass

from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OptimizationConstraints:
    """Portfolio optimization constraints."""
    
    max_single_strategy: float = 0.40  # Max 40% allocation to any strategy
    min_single_strategy: float = 0.05  # Min 5% allocation per strategy
    max_correlation: float = 0.80      # Max correlation between strategies
    min_strategies: int = 3            # Minimum number of strategies
    max_strategies: int = 8            # Maximum number of strategies
    cash_reserve: float = 0.05         # Cash reserve percentage
    max_leverage: float = 1.0          # Maximum leverage multiplier


class PortfolioOptimizer:
    """Main portfolio optimization orchestrator.
    
    This class coordinates different optimization methods and produces
    optimal portfolio allocations based on historical strategy performance.
    
    Attributes:
        method: Optimization method ('mean_variance', 'risk_parity', 'max_div')
        constraints: Portfolio constraints
        risk_free_rate: Risk-free rate for Sharpe ratio calculation
    """
    
    def __init__(
        self,
        method: str = 'mean_variance',
        constraints: Optional[OptimizationConstraints] = None,
        risk_free_rate: float = 0.02  # 2% annual risk-free rate
    ):
        """Initialize portfolio optimizer.
        
        Args:
            method: Optimization method ('mean_variance', 'risk_parity', 'max_div')
            constraints: Portfolio constraints
            risk_free_rate: Annual risk-free rate for Sharpe calculation
        """
        self.method = method
        self.constraints = constraints or OptimizationConstraints()
        self.risk_free_rate = risk_free_rate
        
        # Initialize sub-optimizers
        self.mv_optimizer = MeanVarianceOptimizer(constraints, risk_free_rate)
        self.rp_optimizer = RiskParityOptimizer(constraints)
        self.md_optimizer = MaxDiversificationOptimizer(constraints)
        
        logger.info(
            "Portfolio optimizer initialized",
            method=method,
            max_single=constraints.max_single_strategy if constraints else None
        )
    
    def optimize(
        self,
        returns: pd.DataFrame,
        strategy_names: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """Optimize portfolio allocation.
        
        Args:
            returns: DataFrame with strategy returns (each column is a strategy)
            strategy_names: Optional list of strategy names (uses column names if None)
        
        Returns:
            Dictionary mapping strategy names to optimal weights
        """
        if strategy_names is None:
            strategy_names = returns.columns.tolist()
        
        logger.info(
            "Starting portfolio optimization",
            method=self.method,
            num_strategies=len(strategy_names),
            return_periods=len(returns)
        )
        
        # Calculate expected returns and covariance matrix
        expected_returns = self._calculate_expected_returns(returns)
        cov_matrix = self._calculate_covariance(returns)
        
        # Run appropriate optimization method
        if self.method == 'mean_variance':
            weights = self.mv_optimizer.optimize(expected_returns, cov_matrix)
        elif self.method == 'risk_parity':
            weights = self.rp_optimizer.optimize(cov_matrix)
        elif self.method == 'max_div':
            weights = self.md_optimizer.optimize(expected_returns, cov_matrix)
        else:
            raise ValueError(f"Unknown optimization method: {self.method}")
        
        # Convert to dictionary with strategy names
        allocation = dict(zip(strategy_names, weights))
        
        # Add cash reserve
        total_allocated = sum(allocation.values())
        if total_allocated < 1.0 - self.constraints.cash_reserve:
            # Normalize to accommodate cash reserve
            scale_factor = (1.0 - self.constraints.cash_reserve) / total_allocated
            allocation = {k: v * scale_factor for k, v in allocation.items()}
        
        logger.info(
            "Portfolio optimization complete",
            allocation=allocation,
            total_weight=sum(allocation.values())
        )
        
        return allocation
    
    def _calculate_expected_returns(self, returns: pd.DataFrame) -> np.ndarray:
        """Calculate expected returns for each strategy.
        
        Uses historical mean return as the expected return estimate.
        
        Args:
            returns: DataFrame with strategy returns
        
        Returns:
            Array of expected returns for each strategy
        """
        # Simple historical mean (can be enhanced with exponential weighting)
        return returns.mean().values
    
    def _calculate_covariance(self, returns: pd.DataFrame) -> np.ndarray:
        """Calculate covariance matrix of strategy returns.
        
        Args:
            returns: DataFrame with strategy returns
        
        Returns:
            Covariance matrix
        """
        return returns.cov().values
    
    def calculate_portfolio_metrics(
        self,
        weights: Dict[str, float],
        returns: pd.DataFrame
    ) -> Dict[str, float]:
        """Calculate portfolio-level performance metrics.
        
        Args:
            weights: Strategy allocation weights
            returns: Historical returns DataFrame
        
        Returns:
            Dictionary with portfolio metrics
        """
        # Align weights with returns columns
        weight_array = np.array([weights.get(col, 0) for col in returns.columns])
        
        # Portfolio returns
        portfolio_returns = (returns * weight_array).sum(axis=1)
        
        # Calculate metrics
        annual_return = portfolio_returns.mean() * 252  # Assuming daily returns
        annual_volatility = portfolio_returns.std() * np.sqrt(252)
        sharpe_ratio = (annual_return - self.risk_free_rate) / annual_volatility if annual_volatility > 0 else 0
        
        # Maximum drawdown
        cumulative = (1 + portfolio_returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()
        
        return {
            'annual_return': annual_return,
            'annual_volatility': annual_volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_weight': sum(weights.values())
        }


class MeanVarianceOptimizer:
    """Mean-Variance Optimization (Modern Portfolio Theory).
    
    Maximizes Sharpe ratio (risk-adjusted return) subject to constraints.
    """
    
    def __init__(self, constraints: OptimizationConstraints, risk_free_rate: float):
        """Initialize mean-variance optimizer.
        
        Args:
            constraints: Portfolio constraints
            risk_free_rate: Annual risk-free rate
        """
        self.constraints = constraints
        self.risk_free_rate = risk_free_rate
    
    def optimize(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray
    ) -> np.ndarray:
        """Optimize portfolio to maximize Sharpe ratio.
        
        Args:
            expected_returns: Expected returns for each strategy
            cov_matrix: Covariance matrix of returns
        
        Returns:
            Array of optimal weights
        """
        n = len(expected_returns)
        
        # Use cvxpy for quadratic optimization
        w = cp.Variable(n)
        
        # Portfolio return and variance
        portfolio_return = expected_returns @ w
        portfolio_variance = cp.quad_form(w, cov_matrix)
        
        # Objective: Maximize Sharpe ratio (equivalently, minimize negative Sharpe)
        # We approximate by maximizing return / sqrt(variance)
        # For numerical stability, we maximize return and minimize variance separately
        
        # Alternative formulation: Minimize variance for target return
        # Then iterate to find maximum Sharpe ratio
        
        # Simplified: Maximize return - risk_aversion * variance
        risk_aversion = 0.5
        objective = cp.Maximize(portfolio_return - risk_aversion * portfolio_variance)
        
        # Constraints
        constraints = [
            cp.sum(w) == 1.0 - self.constraints.cash_reserve,  # Weights sum to 1 - cash reserve
            w >= self.constraints.min_single_strategy,         # Minimum weight
            w <= self.constraints.max_single_strategy,         # Maximum weight
        ]
        
        # Solve
        problem = cp.Problem(objective, constraints)
        try:
            problem.solve(solver=cp.ECOS)
            
            if w.value is None:
                logger.warning("Optimization failed, using equal weights")
                return self._equal_weights(n)
            
            weights = np.array(w.value).flatten()
            logger.info("Mean-variance optimization complete", weights=weights.tolist())
            return weights
            
        except Exception as e:
            logger.error("Optimization error", error=str(e))
            return self._equal_weights(n)
    
    def _equal_weights(self, n: int) -> np.ndarray:
        """Fallback to equal weights.
        
        Args:
            n: Number of strategies
        
        Returns:
            Equal weight array
        """
        available = 1.0 - self.constraints.cash_reserve
        return np.ones(n) * (available / n)


class RiskParityOptimizer:
    """Risk Parity Optimization.
    
    Allocates capital so each strategy contributes equally to portfolio risk.
    """
    
    def __init__(self, constraints: OptimizationConstraints):
        """Initialize risk parity optimizer.
        
        Args:
            constraints: Portfolio constraints
        """
        self.constraints = constraints
    
    def optimize(self, cov_matrix: np.ndarray) -> np.ndarray:
        """Optimize for equal risk contribution.
        
        Args:
            cov_matrix: Covariance matrix of returns
        
        Returns:
            Array of optimal weights
        """
        n = cov_matrix.shape[0]
        
        # Objective: Minimize sum of squared differences in risk contributions
        def risk_budget_objective(weights):
            """Calculate risk parity objective function."""
            weights = np.array(weights)
            portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)
            
            if portfolio_vol == 0:
                return 1e10
            
            # Marginal contribution to risk
            marginal_contrib = cov_matrix @ weights
            
            # Risk contribution
            risk_contrib = weights * marginal_contrib / portfolio_vol
            
            # Target equal risk contribution
            target = portfolio_vol / n
            
            # Sum of squared errors
            return np.sum((risk_contrib - target) ** 2)
        
        # Constraints
        cons = (
            {'type': 'eq', 'fun': lambda w: np.sum(w) - (1.0 - self.constraints.cash_reserve)},
        )
        
        # Bounds
        bounds = tuple(
            (self.constraints.min_single_strategy, self.constraints.max_single_strategy)
            for _ in range(n)
        )
        
        # Initial guess: equal weights
        x0 = np.ones(n) * (1.0 - self.constraints.cash_reserve) / n
        
        # Optimize
        try:
            result = minimize(
                risk_budget_objective,
                x0,
                method='SLSQP',
                bounds=bounds,
                constraints=cons,
                options={'maxiter': 1000}
            )
            
            if result.success:
                weights = result.x
                logger.info("Risk parity optimization complete", weights=weights.tolist())
                return weights
            else:
                logger.warning("Risk parity optimization failed, using equal weights")
                return x0
                
        except Exception as e:
            logger.error("Risk parity optimization error", error=str(e))
            return x0


class MaxDiversificationOptimizer:
    """Maximum Diversification Optimization.
    
    Maximizes the diversification ratio, favoring strategies with low correlation.
    """
    
    def __init__(self, constraints: OptimizationConstraints):
        """Initialize max diversification optimizer.
        
        Args:
            constraints: Portfolio constraints
        """
        self.constraints = constraints
    
    def optimize(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray
    ) -> np.ndarray:
        """Optimize for maximum diversification.
        
        Diversification Ratio = (weighted sum of volatilities) / portfolio volatility
        
        Args:
            expected_returns: Expected returns (not used, but kept for consistency)
            cov_matrix: Covariance matrix of returns
        
        Returns:
            Array of optimal weights
        """
        n = cov_matrix.shape[0]
        
        # Individual volatilities
        volatilities = np.sqrt(np.diag(cov_matrix))
        
        # Use cvxpy
        w = cp.Variable(n)
        
        # Objective: Maximize diversification ratio
        # DR = (sum wi * sigma_i) / sqrt(w^T Sigma w)
        # Equivalent to: Minimize portfolio variance while constraining weighted vol to 1
        
        weighted_vol = volatilities @ w
        portfolio_variance = cp.quad_form(w, cov_matrix)
        
        # Objective: Minimize variance / weighted_vol
        # Approximation: Minimize variance with weighted_vol constraint
        objective = cp.Minimize(portfolio_variance)
        
        # Constraints
        constraints = [
            cp.sum(w) == 1.0 - self.constraints.cash_reserve,
            w >= self.constraints.min_single_strategy,
            w <= self.constraints.max_single_strategy,
        ]
        
        # Solve
        problem = cp.Problem(objective, constraints)
        try:
            problem.solve(solver=cp.ECOS)
            
            if w.value is None:
                logger.warning("Max diversification failed, using equal weights")
                return self._equal_weights(n)
            
            weights = np.array(w.value).flatten()
            logger.info("Max diversification optimization complete", weights=weights.tolist())
            return weights
            
        except Exception as e:
            logger.error("Max diversification error", error=str(e))
            return self._equal_weights(n)
    
    def _equal_weights(self, n: int) -> np.ndarray:
        """Fallback to equal weights.
        
        Args:
            n: Number of strategies
        
        Returns:
            Equal weight array
        """
        available = 1.0 - self.constraints.cash_reserve
        return np.ones(n) * (available / n)
