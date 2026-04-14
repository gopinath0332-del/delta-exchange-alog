import os
import json
import logging
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class StateEncoder(json.JSONEncoder):
    """Custom JSON encoder for strategy state that handles NumPy types."""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(StateEncoder, self).default(obj)


# Base directory for state persistence
# Using absolute path resolution relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
STATE_DIR = PROJECT_ROOT / "data" / "state"

def _ensure_state_dir():
    """Ensure state directory exists."""
    if not STATE_DIR.exists():
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created state directory at {STATE_DIR}")

def get_state_path(symbol: str, strategy_name: str) -> Path:
    """Generate persistence path for a symbol/strategy."""
    # Normalize names for filename safety
    safe_symbol = symbol.replace("/", "_").replace("-", "_")
    safe_strategy = strategy_name.replace("/", "_").replace("-", "_")
    return STATE_DIR / f"{safe_symbol}_{safe_strategy}_state.json"

def save_strategy_state(symbol: str, strategy_name: str, state_dict: Dict[str, Any]):
    """Save strategy state to disk."""
    try:
        _ensure_state_dir()
        path = get_state_path(symbol, strategy_name)
        
        # Add metadata
        from datetime import datetime
        state_dict["last_updated"] = datetime.now().isoformat()
        state_dict["symbol"] = symbol
        state_dict["strategy"] = strategy_name

        with open(path, "w") as f:
            json.dump(state_dict, f, indent=4, cls=StateEncoder)
        
        # Only log periodically or on change to avoid log spam? 
        # For now, log briefly.
        logger.debug(f"Saved state for {symbol} ({strategy_name}) to {path.name}")
    except Exception as e:
        logger.error(f"Failed to save state for {symbol}: {e}")

def load_strategy_state(symbol: str, strategy_name: str) -> Optional[Dict[str, Any]]:
    """Load strategy state from disk."""
    try:
        path = get_state_path(symbol, strategy_name)
        if not path.exists():
            return None

        with open(path, "r") as f:
            state = json.load(f)
            logger.info(f"Loaded persistent state for {symbol} ({strategy_name})")
            return state
    except Exception as e:
        logger.warning(f"Failed to load state for {symbol}: {e}")
        return None

def clear_strategy_state(symbol: str, strategy_name: str):
    """Delete state file (e.g., when position is closed)."""
    try:
        path = get_state_path(symbol, strategy_name)
        if path.exists():
            os.remove(path)
            logger.debug(f"Cleared state for {symbol} ({strategy_name})")
    except Exception as e:
        logger.error(f"Failed to clear state for {symbol}: {e}")
