import sys
import os
import logging

# Setup project path
sys.path.append(os.getcwd())

from strategies.bb_breakout_strategy import BBBreakoutStrategy
from strategies.donchian_strategy import DonchianChannelStrategy
from core.persistence import get_state_path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_persistence")

def test_bb_persistence():
    symbol = "BTCUSD"
    strat = BBBreakoutStrategy(symbol=symbol)
    
    # Simulate an entry
    logger.info("Simulating entry for BB Breakout...")
    strat.update_position_state("ENTRY_LONG", 1680000000000, indicators={}, price=30000.0, reason="Test")
    strat.trailing_stop_level = 29000.0
    strat.save_state()
    
    # Check if file exists
    path = get_state_path(symbol, "bb_breakout")
    if path.exists():
        logger.info(f"SUCCESS: State file found at {path}")
    else:
        logger.error(f"FAILURE: State file NOT found at {path}")
        return

    # Re-initialize
    logger.info("Re-initializing BB Strategy...")
    strat2 = BBBreakoutStrategy(symbol=symbol)
    if strat2.current_position == 1 and strat2.entry_price == 30000.0 and strat2.trailing_stop_level == 29000.0:
        logger.info("SUCCESS: State restored correctly!")
    else:
        logger.error(f"FAILURE: State mismatch! Pos={strat2.current_position}, Entry={strat2.entry_price}, TSL={strat2.trailing_stop_level}")

    # Clear state
    logger.info("Clearing state...")
    strat.update_position_state("EXIT_LONG", 1680000001000, indicators={}, price=31000.0, reason="Test exit")
    if not path.exists():
        logger.info("SUCCESS: State file cleared.")
    else:
        logger.error("FAILURE: State file still exists after exit.")

if __name__ == "__main__":
    test_bb_persistence()
