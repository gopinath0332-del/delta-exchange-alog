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
from core.runner import run_strategy_terminal

def main():
    # Load configuration
    config = get_config()
    
    # Setup logging
    setup_logging(
        log_level=config.log_level,
        log_file=config.log_file,
        log_max_bytes=config.log_max_bytes,
        log_backup_count=config.log_backup_count,
        discord_webhook_url=config.discord_webhook_url if config.discord_enabled else None,
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
        }
    ]

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
            
        print(f"\nLaunching {selected_strat['name']}...")
        
        # Hardcoded for now as we only have one mode
        mode = "live" 
        
        run_strategy_terminal(config, selected_strat['monitor'], selected_strat['symbol'], mode)
        
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
    except Exception as e:
        logger.exception("Fatal error in terminal mode")
        print(f"\nFatal Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
