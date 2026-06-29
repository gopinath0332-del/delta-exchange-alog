# New Coin Scanner Architecture

This document contains the architecture diagram and data flow of the New Coin Scanner.

```mermaid
flowchart TD
    A[delta-bot.service\nrun_master_terminal] -->|Spawns Thread| B[Daily 10:00 AM Scheduler]
    B --> C[Fetch candidates: age 7 to 30 days\nGET /v2/products]
    C --> D[Fetch 2H HA candle indicators\nADX, ATR/Price%, EMA20, RVOL]
    D --> E[Fetch daily OI history from data/oi_snapshots.json]
    E --> F{Pass ALL\nEntry Filters?}
    F -->|YES| G[Score, Rank & Save to data/scanner_state.json]
    G --> H[Send Discord Selection Embed with Details]
    F -->|NO| I[Skip Selection]
    
    B --> J[Monitor Active Coins in data/scanner_state.json]
    J --> K[Fetch current stats: Vol, OI, ADX, ATR%]
    K --> L{Fail ANY\nRemoval Rule?}
    L -->|YES| M[Delete from data/scanner_state.json & Send Discord Warning]
    L -->|NO| N[Keep monitoring]
```

## Non-Interference with Live Trading (Safety Principles)

1. **Exception Isolation**: The entire scanning and monitoring logic is enclosed in try-except blocks within a dedicated background thread. Any crash in the scanner cannot crash `delta-bot.service`.
2. **API Rate Limit Integration**: The thread shares the main thread's `DeltaRestClient` instance, utilizing its internal `RateLimiter` sliding window, and inserts a 2-second sleep between requests to avoid starvations.
3. **No Lock Contention**: The thread does not acquire the global `cycle_lock` during API delays, allowing other strategy execution threads to proceed without delay.
