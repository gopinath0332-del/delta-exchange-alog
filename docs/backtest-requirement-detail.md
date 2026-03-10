Create a **professional-grade Python backtesting framework** for
algorithmic trading. The framework must be modular, scalable, and
capable of running multiple strategies on OHLCV data.

## Core Objective

Build a Python application that:

-   Loads OHLCV data from CSV files
-   Dynamically loads trading strategies
-   Runs a full backtest
-   Calculates performance metrics
-   Generates a professional HTML performance report

The system should be structured similar to a **quant trading research
framework**.

------------------------------------------------------------------------

# Data Source

The location of the dataset is defined in a `.env` file:

    DATA_FOLDER=/path/to/data

Inside the folder there are multiple CSV files with the format:

    <symbol>_<timeframe>.csv

Example:

    BTCUSDT_1h.csv
    ETHUSDT_1h.csv
    SOLUSDT_4h.csv

------------------------------------------------------------------------

# CSV File Format

Each CSV file contains the following columns:

    time, open, high, low, close, volume

Details:

-   `time` format: **HH:MM:ss**
-   timezone: **UTC**
-   data is already sorted
-   no missing values

------------------------------------------------------------------------

# System Architecture

The project must follow existing folder structure and create a startup script for backtest

------------------------------------------------------------------------

# Backtest Configuration

Use the following default settings:

    Initial Capital = $1000
    Order Size = 100% of equity
    Pyramiding = 0
    Commission = 0

Rules:

-   Only one position at a time
-   Long and short trades allowed
-   Position size automatically adjusts with equity
-   Refer existing strategy configuration for more details

------------------------------------------------------------------------

# Backtesting Engine Requirements

The engine must:

-   Load all CSV files from the DATA_FOLDER
-   Run the selected strategy on each dataset
-   Track positions
-   Track trades
-   Update equity curve
-   Maintain full trade history

Use **vectorized operations with pandas wherever possible** for
performance.

------------------------------------------------------------------------

# Trade Information

Each trade record must include:

    Symbol
    Entry Time
    Exit Time
    Entry Price
    Exit Price
    Position Type (Long/Short)
    Position Size
    Profit/Loss
    Return %
    Duration

------------------------------------------------------------------------

# Performance Metrics

After the backtest completes calculate:

1.  Strategy name
2.  Initial capital
3.  Final capital
4.  Total return
5.  Sharpe ratio
6.  Sortino ratio
7.  Maximum drawdown
8.  Number of trades
9.  Win rate
10. Profit factor
11. Average win
12. Average loss
13. Average win rate
14. Average loss rate
15. Profitable trades %

------------------------------------------------------------------------

# Report Generation

Generate a **professional HTML report**.

The report should include:

## Summary Section

-   Strategy name
-   Initial capital
-   Final capital
-   Total return
-   Sharpe ratio
-   Sortino ratio
-   Max drawdown
-   Win rate
-   Profit factor

## Charts

Create charts using **Plotly**:

-   Equity curve
-   Drawdown curve

## Tables

Include:

-   Trade list
-   Performance statistics

------------------------------------------------------------------------

# Libraries to Use

Use the following Python libraries:

    pandas
    numpy
    plotly
    python-dotenv
    jinja2
    pathlib
    importlib

Use additional libraries if needed

------------------------------------------------------------------------

# Code Quality Requirements

The code must:

-   Be modular
-   Use classes
-   Include type hints
-   Include docstrings
-   Avoid global variables
-   Follow clean architecture principles

------------------------------------------------------------------------

# Extra Features (Important)

Add these optional capabilities:

1.  Ability to run **single file or all files**
2.  Ability to export trades to CSV
3.  Progress indicator for backtest
4.  Logging system
5.  Handle large datasets efficiently

------------------------------------------------------------------------

# Output

At the end of the backtest:

1.  Print summary results in the terminal
2.  Generate an HTML report:

```{=html}
<!-- -->
```
    reports/backtest_report.html
3. Output HTML reprot for each symbols seperately


------------------------------------------------------------------------

# Final Requirement

Write **complete working Python code for the entire framework**.
