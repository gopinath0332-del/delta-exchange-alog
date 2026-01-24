#!/usr/bin/env python3
"""Portfolio optimization CLI entry point.

This script provides command-line interface for portfolio optimization
and multi-strategy allocation features.
"""

import click
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.logger import setup_logging, get_logger
from core.config import get_config
from portfolio.runner import PortfolioRunner
from portfolio.optimizer import PortfolioOptimizer, OptimizationConstraints
from portfolio.metrics import PerformanceTracker, RiskMetrics
import pandas as pd

logger = get_logger(__name__)


@click.group()
@click.option('--log-level', default='INFO', help='Logging level')
def cli(log_level):
    """Portfolio optimization and multi-strategy allocation CLI."""
    setup_logging(log_level=log_level)


@cli.command()
@click.option('--method', type=click.Choice(['mean_variance', 'risk_parity', 'max_div']),
              default='mean_variance', help='Optimization method')
@click.option('--mode', type=click.Choice(['live', 'paper']), default='paper',
              help='Trading mode')
def run(method, mode):
    """Run portfolio in live or paper trading mode.
    
    Examples:
        # Run with mean-variance optimization in paper mode
        python run_portfolio.py run --method mean_variance --mode paper
        
        # Run with risk parity in live mode
        python run_portfolio.py run --method risk_parity --mode live
    """
    logger.info("Starting portfolio", method=method, mode=mode)
    
    config = get_config()
    
    # Initialize portfolio runner
    runner = PortfolioRunner(config)
    
    # Run portfolio
    runner.run(mode=mode)


@cli.command()
@click.option('--lookback-days', default=30, help='Days of history to analyze')
def optimize(lookback_days):
    """Run portfolio optimization and show recommended allocation.
    
    Examples:
        # Optimize with default 30 days lookback
        python run_portfolio.py optimize
        
        # Optimize with 60 days lookback
        python run_portfolio.py optimize --lookback-days 60
    """
    logger.info("Running portfolio optimization", lookback_days=lookback_days)
    
    config = get_config()
    
    # Initialize components
    runner = PortfolioRunner(config)
    runner.initialize_strategies()
    
    # Get optimal allocation
    allocation = runner.optimize_allocation()
    
    # Calculate capital allocation
    capital_allocation = runner.allocator.calculate_capital_allocation(allocation)
    
    # Display results
    click.echo("\n" + "=" * 60)
    click.echo("PORTFOLIO OPTIMIZATION RESULTS")
    click.echo("=" * 60)
    click.echo(f"\nOptimization Method: {runner.optimizer.method}")
    click.echo(f"Total Capital: ${runner.allocator.total_capital:,.2f}")
    click.echo(f"Cash Reserve: {runner.optimizer.constraints.cash_reserve:.1%}")
    click.echo("\nOptimal Allocation:")
    click.echo("-" * 60)
    
    for strategy, weight in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
        capital = capital_allocation[strategy]
        click.echo(f"  {strategy:20s}: {weight:6.1%}  (${capital:10,.2f})")
    
    click.echo("-" * 60)
    click.echo(f"  {'Total Allocated':20s}: {sum(allocation.values()):6.1%}  (${sum(capital_allocation.values()):10,.2f})")
    click.echo(f"  {'Cash Reserve':20s}: {runner.optimizer.constraints.cash_reserve:6.1%}  (${runner.allocator.total_capital * runner.optimizer.constraints.cash_reserve:10,.2f})")
    click.echo("=" * 60 + "\n")


@cli.command()
def show_allocation():
    """Show current portfolio allocation.
    
    Examples:
        python run_portfolio.py show-allocation
    """
    logger.info("Showing current allocation")
    
    config = get_config()
    runner = PortfolioRunner(config)
    
    # Get current allocation from database
    tracker = runner.tracker
    
    click.echo("\n" + "=" * 60)
    click.echo("CURRENT PORTFOLIO ALLOCATION")
    click.echo("=" * 60)
    click.echo("\nCurrent allocation will be displayed here")
    click.echo("(Requires implementation of query from database)")
    click.echo("=" * 60 + "\n")


@cli.command()
@click.option('--strategy', help='Strategy name (optional, shows all if not specified)')
@click.option('--days', default=30, help='Days of history to show')
def performance(strategy, days):
    """Show performance metrics for strategies.
    
    Examples:
        # Show all strategies
        python run_portfolio.py performance
        
        # Show specific strategy
        python run_portfolio.py performance --strategy double_dip_rsi --days 60
    """
    logger.info("Showing performance metrics", strategy=strategy, days=days)
    
    config = get_config()
    tracker = PerformanceTracker()
    
    click.echo("\n" + "=" * 60)
    click.echo("PORTFOLIO PERFORMANCE METRICS")
    click.echo("=" * 60)
    
    if strategy:
        # Show specific strategy
        returns = tracker.get_strategy_returns(strategy, days)
        
        if len(returns) > 0:
            metrics = RiskMetrics.calculate_all_metrics(returns)
            
            click.echo(f"\nStrategy: {strategy}")
            click.echo(f"Lookback: {days} days")
            click.echo("-" * 60)
            click.echo(f"  Annual Return:     {metrics['return_pct']:>8.2%}")
            click.echo(f"  Volatility:        {metrics['volatility']:>8.2%}")
            click.echo(f"  Sharpe Ratio:      {metrics['sharpe_ratio']:>8.2f}")
            click.echo(f"  Sortino Ratio:     {metrics['sortino_ratio']:>8.2f}")
            click.echo(f"  Max Drawdown:      {metrics['max_drawdown']:>8.2%}")
            click.echo(f"  Win Rate:          {metrics['win_rate']:>8.2%}")
            click.echo(f"  Profit Factor:     {metrics['profit_factor']:>8.2f}")
            click.echo(f"  Calmar Ratio:      {metrics['calmar_ratio']:>8.2f}")
        else:
            click.echo(f"\nNo data available for {strategy}")
    else:
        # Show all strategies
        click.echo("\nAll strategies performance coming soon")
        click.echo("(Requires implementation)")
    
    click.echo("=" * 60 + "\n")


@cli.command()
def rebalance():
    """Manually trigger portfolio rebalancing.
    
    Examples:
        python run_portfolio.py rebalance
    """
    logger.info("Manual rebalancing triggered")
    
    config = get_config()
    runner = PortfolioRunner(config)
    runner.initialize_strategies()
    
    # Get new allocation
    new_allocation = runner.optimize_allocation()
    
    click.echo("\n" + "=" * 60)
    click.echo("PORTFOLIO REBALANCING")
    click.echo("=" * 60)
    click.echo("\nNew Recommended Allocation:")
    
    capital_allocation = runner.allocator.calculate_capital_allocation(new_allocation)
    
    for strategy, weight in sorted(new_allocation.items(), key=lambda x: x[1], reverse=True):
        capital = capital_allocation[strategy]
        click.echo(f"  {strategy:20s}: {weight:6.1%}  (${capital:10,.2f})")
    
    click.echo("=" * 60 + "\n")
    
    if click.confirm('Do you want to execute this rebalancing?'):
        # Execute rebalancing
        runner.allocator.set_target_allocation(new_allocation)
        runner.allocator.execute_rebalance()
        
        # Record in database
        runner.tracker.record_rebalancing(
            trigger_type='manual',
            old_weights=runner.allocator.current_weights,
            new_weights=new_allocation,
            reason='Manual rebalancing triggered by user'
        )
        
        click.echo("✓ Rebalancing executed successfully")
    else:
        click.echo("Rebalancing cancelled")


@cli.command()
@click.option('--start-date', help='Start date (YYYY-MM-DD)')
@click.option('--end-date', help='End date (YYYY-MM-DD)')
def backtest(start_date, end_date):
    """Backtest portfolio allocation strategy.
    
    Examples:
        python run_portfolio.py backtest --start-date 2024-01-01 --end-date 2024-12-31
    """
    logger.info("Backtesting portfolio", start_date=start_date, end_date=end_date)
    
    click.echo("\n" + "=" * 60)
    click.echo("PORTFOLIO BACKTEST")
    click.echo("=" * 60)
    click.echo("\nBacktesting functionality coming soon")
    click.echo("This will compare portfolio performance vs individual strategies")
    click.echo("=" * 60 + "\n")


@cli.command()
def dashboard():
    """Display live portfolio dashboard.
    
    Examples:
        python run_portfolio.py dashboard
    """
    logger.info("Starting portfolio dashboard")
    
    click.echo("\n" + "=" * 60)
    click.echo("PORTFOLIO DASHBOARD")
    click.echo("=" * 60)
    click.echo("\nLive dashboard coming soon")
    click.echo("Will display:")
    click.echo("  - Current allocations")
    click.echo("  - Real-time P&L")
    click.echo("  - Strategy performance")
    click.echo("  - Risk metrics")
    click.echo("=" * 60 + "\n")


if __name__ == '__main__':
    cli()
