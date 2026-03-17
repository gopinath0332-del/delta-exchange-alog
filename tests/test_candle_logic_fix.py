import pandas as pd
import time
from core.candle_utils import get_closed_candle_index
from strategies.donchian_strategy import DonchianChannelStrategy

def test_get_closed_candle_index():
    # Mock data for 1h candles
    # Last candle started at 21:00 (3600s duration)
    last_candle_ts = 1710711000  # 2026-03-17 21:00:00 (approx)
    df = pd.DataFrame({'time': [last_candle_ts - 3600, last_candle_ts], 'close': [70, 71], 'high': [72, 72], 'low': [69, 69]})
    
    # Case 1: Current time is 21:30 (Candle NOT closed)
    time_2130 = (last_candle_ts + 1800) * 1000 
    idx = get_closed_candle_index(df, time_2130, '1h')
    assert idx == -2, f"Expected -2 at 21:30, got {idx}"
    
    # Case 2: Current time is 22:05 (Candle CLOSED)
    time_2205 = (last_candle_ts + 3900) * 1000
    idx = get_closed_candle_index(df, time_2205, '1h')
    assert idx == -1, f"Expected -1 at 22:05, got {idx}"
    
    # Case 3: Current time is 22:40 (Still same candle CLOSED)
    time_2240 = (last_candle_ts + 6000) * 1000
    idx = get_closed_candle_index(df, time_2240, '1h')
    assert idx == -1, f"Expected -1 at 22:40, got {idx}"

def test_one_action_per_candle():
    strat = DonchianChannelStrategy()
    strat.timeframe = '1h'
    strat.allow_short = True
    strat.trade_mode = "Both"
    strat.min_long_days = 0 # No duration gate
    
    # Last candle closed at 21:00
    last_candle_ts = 1710711000
    # Fill enough bars for indicators
    df_len = 110 # Enough for EMA 100
    df = pd.DataFrame({
        'time': [last_candle_ts - 3600*i for i in range(df_len-1, -1, -1)],
        'close': [100.0]*df_len,
        'high': [100.0]*df_len,
        'low': [100.0]*df_len
    })
    
    # 1. Trigger an action at 22:05 (based on 21:00 candle)
    # Mock breakdown: Close 60 < Lower[prev] 100 AND below EMA (~100)
    df.loc[df_len-1, 'close'] = 60.0
    df.loc[df_len-1, 'low'] = 60.0
    df.loc[df_len-1, 'high'] = 60.0
    
    current_time_ms = (last_candle_ts + 3900) * 1000 # 22:05
    action, reason = strat.check_signals(df, current_time_ms)
    
    assert action == "ENTRY_SHORT", f"Short signal should have triggered, got {action} ({reason})"
    assert strat.last_action_candle_ts == last_candle_ts, "Should have recorded action candle TS"
    
    # 2. Try to trigger another action at 22:15 (same candle)
    # Even if we "flip" it back to flat manually in the test
    strat.current_position = 0 
    current_time_ms_2 = (last_candle_ts + 4500) * 1000 # 22:15
    action2, reason2 = strat.check_signals(df, current_time_ms_2)
    
    assert action2 is None, "Signal should NOT have triggered twice on same candle"
    assert "One action per candle rule" in reason2

if __name__ == "__main__":
    try:
        test_get_closed_candle_index()
        print("✓ test_get_closed_candle_index passed")
        test_one_action_per_candle()
        print("✓ test_one_action_per_candle passed")
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
