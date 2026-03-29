import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

# Mocking parts of DonchianChannelStrategy for testing _save_to_disk
class MockStrategy:
    def __init__(self, symbol):
        self.symbol = symbol
        self.current_position = 0
        self.partial_exit_done = False
        self.milestones_hit = [False, False]
        self.entry_price = None
        self.tp_level = None
        self.trailing_stop_level = None
        self.initial_sl_price = None

    def _save_to_disk(self):
        # Import inside for mock
        from core.persistence import save_strategy_state, clear_strategy_state
        try:
            if self.current_position == 0:
                print(f"[{self.symbol}] Position is 0, clearing state...")
                clear_strategy_state(self.symbol, "donchian_channel")
                return

            state = {
                "partial_exit_done": self.partial_exit_done,
                "milestones_hit": self.milestones_hit,
                "entry_price": self.entry_price,
                "tp_level": self.tp_level,
                "trailing_stop_level": self.trailing_stop_level,
                "initial_sl_price": self.initial_sl_price,
                "current_position": self.current_position
            }
            print(f"[{self.symbol}] Position is {self.current_position}, saving state...")
            save_strategy_state(self.symbol, "donchian_channel", state)
        except Exception as e:
            print(f"Error: {e}")

def test_persistence():
    from core.persistence import get_state_path
    
    symbol = "TESTUSD"
    strat = MockStrategy(symbol)
    path = get_state_path(symbol, "donchian_channel")
    
    # 1. Start with position 1
    strat.current_position = 1
    strat.entry_price = 100.0
    strat._save_to_disk()
    if path.exists():
        print(f"CHECK: File created at {path}")
    else:
        print(f"FAIL: File not created at {path}")
        return

    # 2. Change position to 0
    strat.current_position = 0
    strat.entry_price = None
    strat._save_to_disk()
    if not path.exists():
        print(f"CHECK: File deleted successfully.")
    else:
        print(f"FAIL: File still exists at {path}")

if __name__ == "__main__":
    test_persistence()
