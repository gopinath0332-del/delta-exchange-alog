"""Multi-strategy portfolio execution engine.

This module coordinates the execution of multiple trading strategies simultaneously
with optimal capital allocation determined by portfolio optimization.
"""

import time
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import pandas as pd
import yaml
from pathlib import Path

from core.logger import get_logger
from core.config import Config
from api.rest_client import DeltaRestClient
from portfolio.optimizer import PortfolioOptimizer, OptimizationConstraints
from portfolio.allocator import AllocationManager
from portfolio.metrics import PerformanceTracker, RiskMetrics
from notifications.manager import NotificationManager

# Import strategies
from strategies.double_dip_rsi import DoubleDipRSI
from strategies.rsi_200_ema_strategy import RSI200EMAStrategy
from strategies.macd_psar_100ema_strategy import MACDPSAR100EMAStrategy
from strategies.cci_ema_strategy import CCIEMAStrategy
from strategies.rsi_50_ema_strategy import RSI50EMAStrategy

logger = get_logger(__name__)


class PortfolioRunner:
    """Multi-strategy portfolio execution engine.
    
    Coordinates multiple trading strategies running simultaneously with
    optimal capital allocation.
    
    Attributes:
        config: Application configuration
        portfolio_config: Portfolio-specific configuration
        optimizer: Portfolio optimizer
        allocator: Allocation manager
        tracker: Performance tracker
        strategies: Dictionary of active strategy instances
    """
    
    def __init__(
        self,
        config: Config,
        portfolio_config_path: str = "config/portfolio_optimization.yaml"
    ):
        """Initialize portfolio runner.
        
        Args:
            config: Application configuration
            portfolio_config_path: Path to portfolio configuration file
        """
        self.config = config
        self.portfolio_config = self._load_portfolio_config(portfolio_config_path)
        
        # Initialize components
        self.client = DeltaRestClient(config)
        self.notification_manager = NotificationManager(config)
        
        # Extract portfolio settings
        portfolio_settings = self.portfolio_config.get('portfolio', {})
        constraints_dict = portfolio_settings.get('constraints', {})
        
        # Create optimization constraints
        constraints = OptimizationConstraints(
            max_single_strategy=constraints_dict.get('max_single_strategy', 0.40),
            min_single_strategy=constraints_dict.get('min_single_strategy', 0.05),
            max_correlation=constraints_dict.get('max_correlation', 0.80),
            min_strategies=constraints_dict.get('min_strategies', 3),
            max_strategies=constraints_dict.get('max_strategies', 8),
            cash_reserve=constraints_dict.get('cash_reserve', 0.05),
            max_leverage=constraints_dict.get('max_leverage', 1.0)
        )
        
        # Initialize optimizer
        optimization_method = portfolio_settings.get('optimization_method', 'mean_variance')
        risk_free_rate = self.portfolio_config.get('risk_free_rate', 0.02)
        
        self.optimizer = PortfolioOptimizer(
            method=optimization_method,
            constraints=constraints,
            risk_free_rate=risk_free_rate
        )
        
        # Initialize allocator
        total_capital = portfolio_settings.get('total_capital', 10000)
        rebalancing = portfolio_settings.get('rebalancing', {})
        
        self.allocator = AllocationManager(
            total_capital=total_capital,
            rebalancing_method=rebalancing.get('method', 'threshold'),
            rebalancing_threshold=rebalancing.get('threshold', 0.05),
            rebalancing_frequency=rebalancing.get('frequency', 'weekly')
        )
        
        # Initialize tracker
        perf_config = self.portfolio_config.get('performance', {})
        db_path = perf_config.get('database_path', 'data/portfolio_performance.db')
        self.tracker = PerformanceTracker(db_path=db_path)
        
        # Strategy instances
        self.strategies: Dict[str, object] = {}
        self.strategy_returns: pd.DataFrame = pd.DataFrame()
        
        logger.info(
            "Portfolio runner initialized",
            method=optimization_method,
            capital=total_capital,
            num_strategies_available=len(self.portfolio_config.get('strategies', []))
        )
    
    def _load_portfolio_config(self, config_path: str) -> dict:
        """Load portfolio configuration from YAML file.
        
        Args:
            config_path: Path to portfolio configuration file
        
        Returns:
            Portfolio configuration dictionary
        """
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        logger.info("Portfolio configuration loaded", path=config_path)
        return config
    
    def initialize_strategies(self) -> None:
        """Initialize all enabled strategies from configuration."""
        strategy_configs = self.portfolio_config.get('strategies', [])
        
        # Strategy class mapping
        strategy_classes = {
            'double_dip_rsi': DoubleDipRSI,
            'rsi_200_ema': RSI200EMAStrategy,
            'macd_psar_100ema': MACDPSAR100EMAStrategy,
            'cci_ema': CCIEMAStrategy,
            'rsi_50_ema': RSI50EMAStrategy,
        }
        
        for strategy_config in strategy_configs:
            if not strategy_config.get('enabled', False):
                continue
            
            strategy_name = strategy_config['name']
            strategy_class = strategy_classes.get(strategy_name)
            
            if strategy_class is None:
                logger.warning(f"Unknown strategy: {strategy_name}")
                continue
            
            try:
                # Initialize strategy
                # Note: Each strategy class may have different __init__ parameters
                # This is a simplified version - in production, you'd need to handle
                # different initialization patterns
                strategy_instance = strategy_class()
                self.strategies[strategy_name] = {
                    'instance': strategy_instance,
                    'symbol': strategy_config['symbol'],
                    'timeframe': strategy_config['timeframe'],
                    'candle_type': strategy_config.get('candle_type', 'standard'),
                    'description': strategy_config.get('description', '')
                }
                
                logger.info(
                    "Strategy initialized",
                    strategy=strategy_name,
                    symbol=strategy_config['symbol'],
                    timeframe=strategy_config['timeframe']
                )
                
            except Exception as e:
                logger.error(
                    "Failed to initialize strategy",
                    strategy=strategy_name,
                    error=str(e)
                )
    
    def optimize_allocation(self) -> Dict[str, float]:
        """Run portfolio optimization to determine optimal allocation.
        
        Returns:
            Dictionary mapping strategy names to optimal weights
        """
        logger.info("Starting portfolio optimization")
        
        # Get historical returns for each strategy
        lookback_days = self.portfolio_config.get('performance', {}).get('min_history_days', 30)
        
        returns_data = {}
        for strategy_name in self.strategies.keys():
            returns = self.tracker.get_strategy_returns(strategy_name, lookback_days)
            if len(returns) > 0:
                returns_data[strategy_name] = returns
        
        if len(returns_data) < self.optimizer.constraints.min_strategies:
            logger.warning(
                "Insufficient strategy history for optimization",
                available=len(returns_data),
                required=self.optimizer.constraints.min_strategies
            )
            # Fallback to equal weights
            return self._equal_weight_allocation()
        
        # Align returns to same index
        returns_df = pd.DataFrame(returns_data)
        returns_df = returns_df.dropna()  # Remove rows with missing data
        
        # Run optimization
        try:
            optimal_weights = self.optimizer.optimize(returns_df)
            logger.info("Optimization complete", weights=optimal_weights)
            return optimal_weights
        except Exception as e:
            logger.error("Optimization failed", error=str(e))
            return self._equal_weight_allocation()
    
    def _equal_weight_allocation(self) -> Dict[str, float]:
        """Fallback to equal weight allocation.
        
        Returns:
            Equal weights for all strategies
        """
        num_strategies = len(self.strategies)
        cash_reserve = self.optimizer.constraints.cash_reserve
        available = 1.0 - cash_reserve
        equal_weight = available / num_strategies
        
        return {name: equal_weight for name in self.strategies.keys()}
    
    def run(self, mode: str = 'paper') -> None:
        """Run portfolio in live or paper trading mode.
        
        Args:
            mode: 'live' or 'paper'
        """
        logger.info("Starting portfolio execution", mode=mode)
        
        # Initialize strategies
        self.initialize_strategies()
        
        # Initial optimization
        optimal_weights = self.optimize_allocation()
        self.allocator.set_target_allocation(optimal_weights)
        
        # Calculate capital allocation
        capital_allocation = self.allocator.calculate_capital_allocation(optimal_weights)
        
        # Record initial allocation
        self.tracker.record_allocation(
            optimal_weights,
            capital_allocation,
            self.optimizer.method
        )
        
        # Send notification
        self.notification_manager.send_info(
            "Portfolio Started",
            f"Running {len(self.strategies)} strategies in {mode} mode\n"
            f"Optimization: {self.optimizer.method}\n"
            f"Allocation: {optimal_weights}"
        )
        
        logger.info(
            "Portfolio started",
            mode=mode,
            strategies=list(self.strategies.keys()),
            allocation=capital_allocation
        )
        
        # Main execution loop
        try:
            while True:
                # Execute each strategy
                self._execute_strategies(mode, capital_allocation)
                
                # Check if rebalancing needed
                self._check_rebalancing()
                
                # Update performance metrics
                self._update_metrics()
                
                # Sleep before next iteration
                time.sleep(60)  # Check every minute
                
        except KeyboardInterrupt:
            logger.info("Portfolio execution stopped by user")
            self.notification_manager.send_info(
                "Portfolio Stopped",
                "Portfolio execution stopped by user"
            )
    
    def _execute_strategies(
        self,
        mode: str,
        capital_allocation: Dict[str, float]
    ) -> None:
        """Execute all strategies with allocated capital.
        
        Args:
            mode: Trading mode (live or paper)
            capital_allocation: Capital allocated to each strategy
        """
        for strategy_name, strategy_data in self.strategies.items():
            try:
                allocated_capital = capital_allocation.get(strategy_name, 0.0)
                
                # Execute strategy (simplified - actual implementation would
                # integrate with core/runner.py)
                # This is where you'd call the strategy's check_signals method
                # and execute trades based on allocated capital
                
                logger.debug(
                    "Strategy tick",
                    strategy=strategy_name,
                    capital=allocated_capital
                )
                
            except Exception as e:
                logger.error(
                    "Strategy execution error",
                    strategy=strategy_name,
                    error=str(e)
                )
    
    def _check_rebalancing(self) -> None:
        """Check if portfolio needs rebalancing and execute if needed."""
        # Get current strategy values (simplified - would query actual positions)
        current_values = self._get_current_strategy_values()
        
        # Update current weights
        self.allocator.update_current_weights(current_values)
        
        # Check if rebalancing needed
        needs_rebalance, trigger, reason = self.allocator.needs_rebalancing()
        
        if needs_rebalance:
            logger.info("Rebalancing triggered", trigger=trigger, reason=reason)
            
            # Calculate new allocation
            new_weights = self.optimize_allocation()
            
            # Record rebalancing
            self.tracker.record_rebalancing(
                trigger_type=trigger.value if trigger else 'unknown',
                old_weights=self.allocator.current_weights,
                new_weights=new_weights,
                reason=reason
            )
            
            # Update allocation
            self.allocator.set_target_allocation(new_weights)
            self.allocator.execute_rebalance()
            
            # Notify
            self.notification_manager.send_info(
                "Portfolio Rebalanced",
                f"Trigger: {trigger}\nReason: {reason}\nNew allocation: {new_weights}"
            )
    
    def _get_current_strategy_values(self) -> Dict[str, float]:
        """Get current market value of each strategy's positions.
        
        Returns:
            Dictionary mapping strategy names to current values
        """
        # Simplified implementation - would query actual position values
        # from the exchange via self.client
        return {name: 0.0 for name in self.strategies.keys()}
    
    def _update_metrics(self) -> None:
        """Update performance metrics for all strategies."""
        for strategy_name in self.strategies.keys():
            try:
                # Calculate metrics (simplified - would use actual trade history)
                # In production, you'd calculate these from the strategy's trade history
                
                # Placeholder metrics
                metrics = {
                    'return_pct': 0.0,
                    'volatility': 0.0,
                    'sharpe_ratio': 0.0,
                    'sortino_ratio': 0.0,
                    'max_drawdown': 0.0,
                    'win_rate': 0.0,
                    'profit_factor': 1.0,
                    'total_trades': 0
                }
                
                # Record metrics
                # self.tracker.record_strategy_performance(strategy_name, metrics)
                
            except Exception as e:
                logger.error(
                    "Metrics update error",
                    strategy=strategy_name,
                    error=str(e)
                )
