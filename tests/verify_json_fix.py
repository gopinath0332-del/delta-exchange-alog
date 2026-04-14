import sys
import os
import numpy as np
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.persistence import save_strategy_state, load_strategy_state, get_state_path

def test_numpy_persistence():
    symbol = "TEST_NP"
    strategy_name = "donchian_channel"
    
    state = {
        "current_position": np.int64(1),
        "entry_price": np.float64(0.01883),
        "last_action_candle_ts": np.int64(1713060000000),
        "milestones_hit": [np.bool_(True), False],
        "arr": np.array([1, 2, 3])
    }
    
    path = get_state_path(symbol, strategy_name)
    if path.exists():
        os.remove(path)
        
    print(f"Testing save_strategy_state for {symbol} with NumPy types...")
    save_strategy_state(symbol, strategy_name, state)
    
    if not path.exists():
        print("Save FAILED (No file created)")
        return False
        
    print("Save SUCCESSFUL")

    print("Testing load_strategy_state...")
    loaded_state = load_strategy_state(symbol, strategy_name)
    if loaded_state:
        print("Load SUCCESSFUL")
        print(f"current_position: {loaded_state.get('current_position')} (Type: {type(loaded_state.get('current_position'))})")
        print(f"entry_price: {loaded_state.get('entry_price')} (Type: {type(loaded_state.get('entry_price'))})")
        
        # Verify types are standard Python types now
        assert isinstance(loaded_state.get('current_position'), int)
        assert isinstance(loaded_state.get('entry_price'), float)
        assert isinstance(loaded_state.get('last_action_candle_ts'), int)
        assert isinstance(loaded_state.get('arr'), list)
        
        print("Type verification SUCCESSFUL")
        return True
    else:
        print("Load FAILED")
        return False

if __name__ == "__main__":
    if test_numpy_persistence():
        print("\nALL PERSISTENCE TESTS PASSED")
        sys.exit(0)
    else:
        print("\nTESTS FAILED")
        sys.exit(1)
