-- SQLite Database Schema for Portfolio Optimization
-- This schema tracks portfolio performance, allocations, correlations, and rebalancing history

-- Strategy Performance History
-- Stores performance metrics for each strategy over time
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
    total_trades INTEGER,
    INDEX idx_strategy_time (strategy_name, timestamp)
);

-- Portfolio Allocations
-- Tracks how capital is allocated across strategies
CREATE TABLE IF NOT EXISTS portfolio_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    strategy_name TEXT NOT NULL,
    weight REAL NOT NULL,
    capital_allocated REAL NOT NULL,
    optimization_method TEXT NOT NULL,
    INDEX idx_allocation_time (timestamp)
);

-- Correlation Matrix
-- Stores pairwise correlations between strategies
CREATE TABLE IF NOT EXISTS correlation_matrix (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    strategy_a TEXT NOT NULL,
    strategy_b TEXT NOT NULL,
    correlation REAL NOT NULL,
    INDEX idx_corr_time (timestamp)
);

-- Rebalancing History
-- Tracks when and why portfolio was rebalanced
CREATE TABLE IF NOT EXISTS rebalancing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    trigger_type TEXT NOT NULL,
    old_weights TEXT NOT NULL,
    new_weights TEXT NOT NULL,
    reason TEXT,
    INDEX idx_rebalance_time (timestamp)
);

-- Portfolio Summary Statistics
-- Daily portfolio-level metrics
CREATE TABLE IF NOT EXISTS portfolio_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    total_value REAL NOT NULL,
    total_return_pct REAL,
    portfolio_volatility REAL,
    portfolio_sharpe REAL,
    num_active_strategies INTEGER,
    INDEX idx_stats_time (timestamp)
);
