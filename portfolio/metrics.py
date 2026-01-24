"""Portfolio performance tracking and risk metrics calculation.

This module provides tools for tracking strategy performance over time,
calculating risk metrics at both strategy and portfolio levels, and
maintaining correlation matrices.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import sqlite3
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)


class PerformanceTracker:
    """Tracks historical performance of strategies and portfolios.
    
    Stores performance metrics in a SQLite database for historical analysis
    and optimization.
    
    Attributes:
        db_path: Path to SQLite database
    """
    
    def __init__(self, db_path: str = "data/portfolio_performance.db"):
        """Initialize performance tracker.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_database()
        
        logger.info("Performance tracker initialized", db_path=db_path)
    
    def _ensure_database(self) -> None:
        """Ensure database and tables exist."""
        # Create directory if needed
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Create tables
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Strategy performance table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS strategy_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                return_pct REAL,
                volatility REAL,
                sharpe_ratio REAL,
                sortino_ratio REAL,
                max_drawdown REAL,
                win_rate REAL,
                profit_factor REAL,
                total_trades INTEGER
            )
        ''')
        
        # Portfolio allocations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                strategy_name TEXT NOT NULL,
                weight REAL NOT NULL,
                capital_allocated REAL NOT NULL,
                optimization_method TEXT NOT NULL
            )
        ''')
        
        # Correlation matrix table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS correlation_matrix (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                strategy_a TEXT NOT NULL,
                strategy_b TEXT NOT NULL,
                correlation REAL NOT NULL
            )
        ''')
        
        # Rebalancing history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rebalancing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                trigger_type TEXT NOT NULL,
                old_weights TEXT NOT NULL,
                new_weights TEXT NOT NULL,
                reason TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def record_strategy_performance(
        self,
        strategy_name: str,
        metrics: Dict[str, float],
        timestamp: Optional[datetime] = None
    ) -> None:
        """Record strategy performance metrics.
        
        Args:
            strategy_name: Name of the strategy
            metrics: Dictionary with performance metrics
            timestamp: Timestamp for the record (uses now() if None)
        """
        timestamp = timestamp or datetime.now()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO strategy_performance
            (strategy_name, timestamp, return_pct, volatility, sharpe_ratio, 
             sortino_ratio, max_drawdown, win_rate, profit_factor, total_trades)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            strategy_name,
            timestamp,
            metrics.get('return_pct'),
            metrics.get('volatility'),
            metrics.get('sharpe_ratio'),
            metrics.get('sortino_ratio'),
            metrics.get('max_drawdown'),
            metrics.get('win_rate'),
            metrics.get('profit_factor'),
            metrics.get('total_trades', 0)
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(
            "Strategy performance recorded",
            strategy=strategy_name,
            sharpe=metrics.get('sharpe_ratio')
        )
    
    def record_allocation(
        self,
        allocations: Dict[str, float],
        capital_amounts: Dict[str, float],
        optimization_method: str,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Record portfolio allocation.
        
        Args:
            allocations: Strategy weight allocations
            capital_amounts: Capital allocated to each strategy
            optimization_method: Optimization method used
            timestamp: Timestamp for the record
        """
        timestamp = timestamp or datetime.now()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for strategy, weight in allocations.items():
            capital = capital_amounts.get(strategy, 0.0)
            cursor.execute('''
                INSERT INTO portfolio_allocations
                (timestamp, strategy_name, weight, capital_allocated, optimization_method)
                VALUES (?, ?, ?, ?, ?)
            ''', (timestamp, strategy, weight, capital, optimization_method))
        
        conn.commit()
        conn.close()
        
        logger.info("Portfolio allocation recorded", method=optimization_method)
    
    def record_correlation(
        self,
        corr_matrix: pd.DataFrame,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Record correlation matrix.
        
        Args:
            corr_matrix: Correlation matrix DataFrame
            timestamp: Timestamp for the record
        """
        timestamp = timestamp or datetime.now()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        strategies = corr_matrix.index.tolist()
        for i, strategy_a in enumerate(strategies):
            for j, strategy_b in enumerate(strategies):
                if i < j:  # Only record upper triangle (avoid duplicates)
                    corr = corr_matrix.loc[strategy_a, strategy_b]
                    cursor.execute('''
                        INSERT INTO correlation_matrix
                        (timestamp, strategy_a, strategy_b, correlation)
                        VALUES (?, ?, ?, ?)
                    ''', (timestamp, strategy_a, strategy_b, corr))
        
        conn.commit()
        conn.close()
        
        logger.info("Correlation matrix recorded")
    
    def record_rebalancing(
        self,
        trigger_type: str,
        old_weights: Dict[str, float],
        new_weights: Dict[str, float],
        reason: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Record rebalancing event.
        
        Args:
            trigger_type: Type of rebalancing trigger
            old_weights: Weights before rebalancing
            new_weights: Weights after rebalancing
            reason: Reason for rebalancing
            timestamp: Timestamp for the record
        """
        timestamp = timestamp or datetime.now()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO rebalancing_history
            (timestamp, trigger_type, old_weights, new_weights, reason)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, trigger_type, str(old_weights), str(new_weights), reason))
        
        conn.commit()
        conn.close()
        
        logger.info("Rebalancing recorded", trigger=trigger_type, reason=reason)
    
    def get_strategy_returns(
        self,
        strategy_name: str,
        lookback_days: int = 30
    ) -> pd.Series:
        """Get historical returns for a strategy.
        
        Args:
            strategy_name: Name of the strategy
            lookback_days: Number of days to look back
        
        Returns:
            Series of returns
        """
        conn = sqlite3.connect(self.db_path)
        
        query = '''
            SELECT timestamp, return_pct
            FROM strategy_performance
            WHERE strategy_name = ?
            AND timestamp >= datetime('now', ?)
            ORDER BY timestamp
        '''
        
        df = pd.read_sql_query(
            query,
            conn,
            params=(strategy_name, f'-{lookback_days} days')
        )
        
        conn.close()
        
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            return df['return_pct']
        
        return pd.Series(dtype=float)


class RiskMetrics:
    """Calculate risk and performance metrics for strategies and portfolios.
    
    Provides methods to calculate:
    - Sharpe Ratio
    - Sortino Ratio
    - Maximum Drawdown
    - Win Rate
    - Profit Factor
    - Calmar Ratio
    - Diversification Benefit
    """
    
    @staticmethod
    def sharpe_ratio(
        returns: pd.Series,
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252
    ) -> float:
        """Calculate Sharpe ratio.
        
        Args:
            returns: Series of returns
            risk_free_rate: Annual risk-free rate
            periods_per_year: Number of periods per year (252 for daily, 52 for weekly)
        
        Returns:
            Sharpe ratio
        """
        if len(returns) == 0:
            return 0.0
        
        excess_returns = returns - (risk_free_rate / periods_per_year)
        
        if excess_returns.std() == 0:
            return 0.0
        
        sharpe = np.sqrt(periods_per_year) * (excess_returns.mean() / excess_returns.std())
        return float(sharpe)
    
    @staticmethod
    def sortino_ratio(
        returns: pd.Series,
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252
    ) -> float:
        """Calculate Sortino ratio (like Sharpe but only penalizes downside volatility).
        
        Args:
            returns: Series of returns
            risk_free_rate: Annual risk-free rate
            periods_per_year: Number of periods per year
        
        Returns:
            Sortino ratio
        """
        if len(returns) == 0:
            return 0.0
        
        excess_returns = returns - (risk_free_rate / periods_per_year)
        downside_returns = excess_returns[excess_returns < 0]
        
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0.0
        
        sortino = np.sqrt(periods_per_year) * (excess_returns.mean() / downside_returns.std())
        return float(sortino)
    
    @staticmethod
    def max_drawdown(returns: pd.Series) -> float:
        """Calculate maximum drawdown.
        
        Args:
            returns: Series of returns
        
        Returns:
            Maximum drawdown (negative value)
        """
        if len(returns) == 0:
            return 0.0
        
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        
        return float(drawdown.min())
    
    @staticmethod
    def win_rate(returns: pd.Series) -> float:
        """Calculate win rate (percentage of positive returns).
        
        Args:
            returns: Series of returns
        
        Returns:
            Win rate (0-1)
        """
        if len(returns) == 0:
            return 0.0
        
        winning_periods = (returns > 0).sum()
        total_periods = len(returns)
        
        return float(winning_periods / total_periods)
    
    @staticmethod
    def profit_factor(returns: pd.Series) -> float:
        """Calculate profit factor (gross profit / gross loss).
        
        Args:
            returns: Series of returns
        
        Returns:
            Profit factor
        """
        if len(returns) == 0:
            return 0.0
        
        gross_profit = returns[returns > 0].sum()
        gross_loss = abs(returns[returns < 0].sum())
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        
        return float(gross_profit / gross_loss)
    
    @staticmethod
    def calmar_ratio(
        returns: pd.Series,
        periods_per_year: int = 252
    ) -> float:
        """Calculate Calmar ratio (annualized return / max drawdown).
        
        Args:
            returns: Series of returns
            periods_per_year: Number of periods per year
        
        Returns:
            Calmar ratio
        """
        if len(returns) == 0:
            return 0.0
        
        annual_return = returns.mean() * periods_per_year
        max_dd = abs(RiskMetrics.max_drawdown(returns))
        
        if max_dd == 0:
            return 0.0
        
        return float(annual_return / max_dd)
    
    @staticmethod
    def diversification_benefit(
        weights: np.ndarray,
        volatilities: np.ndarray,
        portfolio_volatility: float
    ) -> float:
        """Calculate diversification benefit.
        
        Diversification Benefit = 1 - (portfolio_vol / weighted_sum_of_vols)
        
        Args:
            weights: Portfolio weights
            volatilities: Individual strategy volatilities
            portfolio_volatility: Portfolio volatility
        
        Returns:
            Diversification benefit (0-1, higher is better)
        """
        weighted_vol_sum = np.sum(weights * volatilities)
        
        if weighted_vol_sum == 0:
            return 0.0
        
        db = 1.0 - (portfolio_volatility / weighted_vol_sum)
        return float(max(0.0, db))  # Clamp to non-negative
    
    @staticmethod
    def calculate_all_metrics(
        returns: pd.Series,
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252
    ) -> Dict[str, float]:
        """Calculate all risk metrics for a return series.
        
        Args:
            returns: Series of returns
            risk_free_rate: Annual risk-free rate
            periods_per_year: Number of periods per year
        
        Returns:
            Dictionary with all calculated metrics
        """
        return {
            'return_pct': float(returns.mean() * periods_per_year) if len(returns) > 0 else 0.0,
            'volatility': float(returns.std() * np.sqrt(periods_per_year)) if len(returns) > 0 else 0.0,
            'sharpe_ratio': RiskMetrics.sharpe_ratio(returns, risk_free_rate, periods_per_year),
            'sortino_ratio': RiskMetrics.sortino_ratio(returns, risk_free_rate, periods_per_year),
            'max_drawdown': RiskMetrics.max_drawdown(returns),
            'win_rate': RiskMetrics.win_rate(returns),
            'profit_factor': RiskMetrics.profit_factor(returns),
            'calmar_ratio': RiskMetrics.calmar_ratio(returns, periods_per_year),
        }


class CorrelationAnalyzer:
    """Analyze and track correlation between strategies.
    
    Provides methods to calculate and monitor correlation matrices,
    identifying highly correlated strategies to avoid over-concentration.
    """
    
    @staticmethod
    def calculate_correlation_matrix(
        returns: pd.DataFrame
    ) -> pd.DataFrame:
        """Calculate correlation matrix from returns.
        
        Args:
            returns: DataFrame with strategy returns (columns = strategies)
        
        Returns:
            Correlation matrix DataFrame
        """
        return returns.corr()
    
    @staticmethod
    def find_highly_correlated_pairs(
        corr_matrix: pd.DataFrame,
        threshold: float = 0.80
    ) -> List[Tuple[str, str, float]]:
        """Find pairs of strategies with high correlation.
        
        Args:
            corr_matrix: Correlation matrix
            threshold: Correlation threshold
        
        Returns:
            List of (strategy_a, strategy_b, correlation) tuples
        """
        high_corr_pairs = []
        
        strategies = corr_matrix.index.tolist()
        for i, strategy_a in enumerate(strategies):
            for j, strategy_b in enumerate(strategies):
                if i < j:  # Avoid duplicates and self-correlation
                    corr = abs(corr_matrix.loc[strategy_a, strategy_b])
                    if corr >= threshold:
                        high_corr_pairs.append((strategy_a, strategy_b, float(corr)))
        
        return high_corr_pairs
    
    @staticmethod
    def rolling_correlation(
        returns_a: pd.Series,
        returns_b: pd.Series,
        window: int = 30
    ) -> pd.Series:
        """Calculate rolling correlation between two return series.
        
        Args:
            returns_a: First return series
            returns_b: Second return series
            window: Rolling window size
        
        Returns:
            Series of rolling correlations
        """
        return returns_a.rolling(window=window).corr(returns_b)
