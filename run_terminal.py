#!/usr/bin/env python3
"""
Run the Delta Exchange Trading Bot in Terminal Mode (Headless).
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.config import get_config
from core.logger import setup_logging, get_logger
from core.runner import run_strategy_terminal, run_multi_symbol_terminal

def main():
    # Load configuration
    config = get_config()
    
    # Setup logging with error alerting.
    # Error/Critical messages are sent to DISCORD_ERROR_WEBHOOK_URL (dedicated error channel),
    # NOT to the general DISCORD_WEBHOOK_URL used for trade notifications.
    setup_logging(
        log_level=config.log_level,
        log_file=config.log_file,
        log_max_bytes=config.log_max_bytes,
        log_backup_count=config.log_backup_count,
        discord_error_webhook_url=config.discord_error_webhook_url if config.discord_enabled else None,
        alert_throttle_seconds=config.alert_throttle_seconds,
        enable_error_alerts=config.enable_error_alerts,
    )
    
    logger = get_logger("terminal_launcher")
    logger.info("Starting Terminal Mode Launcher")

    print("\n" + "="*80)
    print(" DELTA EXCHANGE TRADING BOT - TERMINAL MODE")
    print("="*80)
    
    # Available Strategies
    STRATEGIES = [
        {
            "id": 1,
            "name": "BTCUSD Double-Dip RSI (Heikin Ashi)", 
            "symbol": "BTCUSD", 
            "monitor": "double-dip",
            "desc": "Long/Short strategy based on RSI thresholds and duration."
        },
        {
            "id": 2,
            "name": "ETHUSD Double-Dip RSI (Heikin Ashi)", 
            "symbol": "ETHUSD", 
            "monitor": "double-dip",
            "desc": "Long/Short strategy for ETH using same parameters."
        },
        {
            "id": 3,
            "name": "BTCUSD CCI + 50 EMA Strategy (1H Standard)", 
            "symbol": "BTCUSD", 
            "monitor": "cci-ema",
            "timeframe": "1h",
            "candle_type": "standard",  # Changed from Heikin Ashi to standard candles
            "desc": "Long Entry, Partial Exit at ATR Target, Final Exit on Reversal."
        },
        {
            "id": 4,
            "name": "XRPUSD RS-50-EMA Strategy (Heikin Ashi)", 
            "symbol": "XRPUSD", 
            "monitor": "rs-50-ema",
            "desc": "Long Entry: Close > EMA50 & RSI > 40. Exit: Close < EMA50."
        },
        {
            "id": 5,
            "name": "XRPUSD MACD PSAR 100EMA (Heikin Ashi)", 
            "symbol": "XRPUSD", 
            "monitor": "macd_psar_100ema",
            "desc": "Long Only. Entry: Close>EMA100, MACD>0, Price>SAR. Exit: Price<SAR."
        },
        {
            "id": 6,
            "name": "ETHUSD RSI-200-EMA (1H Heikin Ashi)",
            "symbol": "ETHUSD",
            "monitor": "rsi_200_ema",
            "timeframe": "1h",
            "candle_type": "heikin-ashi",
            "desc": "Long Entry: RSI crossover 70 & Close>EMA200. Partial TP, ATR Trail Stop."
        },
        {
            "id": 7,
            "name": "RIVERUSD RSI-Supertrend (1H Standard)",
            "symbol": "RIVERUSD",
            "monitor": "rsi-supertrend",
            "timeframe": "1h",
            "candle_type": "standard",
            "desc": "Long-only with RSI crossover entry and Supertrend exit."
        },
        {
            "id": 8,
            "name": "RIVERUSD Donchian Channel (1H Heikin Ashi)",
            "symbol": "RIVERUSD",
            "monitor": "donchian_channel",
            "timeframe": "1h",
            "candle_type": "heikin-ashi",
            "desc": "Long-only Donchian breakout with ATR-based TP and trailing stop."
        },
        {
            "id": 9,
            "name": "PIPPINUSD Donchian Channel (1H Heikin Ashi)",
            "symbol": "PIPPINUSD",
            "monitor": "donchian_channel",
            "timeframe": "1h",
            "candle_type": "heikin-ashi",
            "desc": "Donchian breakout with 100 EMA trend filter and ATR trailing stop."
        },
        {
            "id": 10,
            "name": "BTCUSD EMA Cross (4H Standard)",
            "symbol": "BTCUSD",
            "monitor": "ema-cross",
            "timeframe": "4h",
            "candle_type": "standard",
            "desc": "Long/Short based on EMA 10/20 crossover."
        },
        {
            # PIUSD Donchian Channel — 4H Standard, 5x leverage, $50 target margin
            # Reuses the existing DonchianChannelStrategy (no new strategy code needed).
            # Start/stop: sudo systemctl start/stop delta-bot-pi
            "id": 11,
            "name": "PIUSD Donchian Channel (4H Standard)",
            "symbol": "PIUSD",
            "monitor": "donchian_channel",
            "timeframe": "4h",
            "candle_type": "standard",
            "desc": "Donchian breakout with 100 EMA trend filter and ATR trailing stop."
        },
        {
            # BERAUSD Donchian Channel — 1H Heikin Ashi, 5x leverage, $50 target margin
            # Reuses the existing DonchianChannelStrategy (no new strategy code needed).
            # Start/stop: sudo systemctl start/stop delta-bot-bera
            "id": 12,
            "name": "BERAUSD Donchian Channel (1H Heikin Ashi)",
            "symbol": "BERAUSD",
            "monitor": "donchian_channel",
            "timeframe": "1h",
            "candle_type": "heikin-ashi",
            "desc": "Donchian breakout with 100 EMA trend filter and ATR trailing stop."
        },
        {
            # PAXGUSD Donchian Channel — 1H Heikin Ashi, 5x leverage, $30 target margin
            # Reuses the existing DonchianChannelStrategy (no new strategy code needed).
            # Config keys: LEVERAGE_PAXG, TARGET_MARGIN_PAXG, ENABLE_ORDER_PLACEMENT_PAXG
            # Start/stop: sudo systemctl start/stop delta-bot-paxg
            "id": 13,
            "name": "PAXGUSD Donchian Channel (1H Heikin Ashi)",
            "symbol": "PAXGUSD",
            "monitor": "donchian_channel",
            "timeframe": "1h",
            "candle_type": "heikin-ashi",
            "desc": "Donchian breakout with 100 EMA trend filter and ATR trailing stop. $30 target margin."
        },
        {
            # Multi-coin Donchian Channel service.
            # Runs PI, PIPPIN, RIVER, BERA, PAXG in parallel threads sharing one
            # DeltaRestClient so API calls are serialized automatically (no rate-limit burst).
            # Each coin gets its own log file and its own Discord startup message.
            # Symbols/log-files are configured in settings.yaml under multi_coin.donchian_channel.
            # On Raspberry Pi this is the entry used by delta-bot-donchian.service.
            "id": 14,
            "name": "Donchian Channel — Multi-Coin (PI, PIPPIN, RIVER, BERA, PAXG)",
            "multi_coin_key": "donchian_channel",  # key under multi_coin in settings.yaml
            "desc": "Runs Donchian Channel for all 5 coins in parallel threads. API calls serialized via shared client."
        }
    ]

    import argparse
    parser = argparse.ArgumentParser(description="Delta Exchange Trading Bot - Terminal Mode")
    parser.add_argument("--strategy", type=int, help="Strategy ID to run (e.g. 1)")
    parser.add_argument("--non-interactive", action="store_true", help="Run in non-interactive mode (requires --strategy)")
    args = parser.parse_args()

    # Strategy Selection Logic
    selected_strat = None
    
    if args.strategy:
        selected_strat = next((s for s in STRATEGIES if s['id'] == args.strategy), None)
        if not selected_strat:
            print(f"Error: Strategy ID {args.strategy} not found.")
            sys.exit(1)
    
    if not selected_strat and not args.non_interactive:
        print("\nAvailable Strategies:")
        for strat in STRATEGIES:
            print(f" {strat['id']}. {strat['name']}")
            print(f"    - {strat['desc']}")
        
        print("\n" + "-"*40)
        
        try:
            choice = input("Select a strategy to run (enter number): ").strip()
            selected_strat = next((s for s in STRATEGIES if str(s['id']) == choice), None)
            
            if not selected_strat:
                print("\nInvalid selection. Exiting.")
                sys.exit(1)
        except KeyboardInterrupt:
            print("\nExiting...")
            sys.exit(0)

    if not selected_strat:
        print("Error: No strategy selected. Use interactive mode or provide --strategy ID.")
        sys.exit(1)
            
    print(f"\nLaunching {selected_strat['name']}...")
    
    # Hardcoded for now as we only have one mode
    mode = "live"

    # -----------------------------------------------------------------------
    # Multi-coin mode — triggered when the strategy entry has 'multi_coin_key'
    # -----------------------------------------------------------------------
    if selected_strat.get("multi_coin_key"):
        strategy_key = selected_strat["multi_coin_key"]

        # Load symbol list from settings.yaml multi_coin section
        multi_coin_cfg = config.settings.get("multi_coin", {})
        strategy_coin_cfg = multi_coin_cfg.get(strategy_key)

        if not strategy_coin_cfg:
            print(
                f"Error: No multi_coin configuration found for '{strategy_key}' "
                f"in settings.yaml. Available: {list(multi_coin_cfg.keys())}"
            )
            sys.exit(1)

        symbols_config = strategy_coin_cfg.get("symbols", [])
        if not symbols_config:
            print(f"Error: 'symbols' list is empty for multi_coin.{strategy_key} in settings.yaml.")
            sys.exit(1)

        logger.info(f"Multi-coin mode: strategy={strategy_key}, symbols={[s['symbol'] for s in symbols_config]}")

        try:
            run_multi_symbol_terminal(config, strategy_key, symbols_config, mode)
        except KeyboardInterrupt:
            print("\nExiting...")
            sys.exit(0)
        except Exception as e:
            logger.exception("Fatal error in multi-coin terminal mode")
            print(f"\nFatal Error: {e}")
            sys.exit(1)
        return  # multi-coin handled above

    # -----------------------------------------------------------------------
    # Single-coin mode: original strategy selection flow
    # -----------------------------------------------------------------------
    try:
        # Get timeframe and candle_type from strategy, default to 1h and heikin-ashi
        timeframe = selected_strat.get('timeframe', '1h')
        candle_type = selected_strat.get('candle_type', 'heikin-ashi')

        run_strategy_terminal(config, selected_strat['monitor'], selected_strat['symbol'], mode, candle_type, timeframe)

    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
    except Exception as e:
        logger.exception("Fatal error in terminal mode")
        print(f"\nFatal Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
