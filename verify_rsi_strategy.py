import pandas as pd
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from strategies.rsi_50_ema_strategy import RSI50EMAStrategy

def test_strategy():
    print("Testing RSI50EMAStrategy...")
    strategy = RSI50EMAStrategy()
    
    # Create synthetic data
    # Case 1: Entry Condition
    # EMA Length = 50. Need > 50 candles.
    
    # Let's assume price goes up.
    prices = [100.0 + i for i in range(100)] 
    # Last price = 199. EMA will be around 199ish? No, lagging.
    
    # Let's force EMA to be lower than Close.
    # Close = 200, EMA = 150.
    # RSI > 40.
    
    data = []
    import math
    for i in range(100):
        price = 100 + i
        # RSI needs variation.
        # Simple uptrend -> RSI high.
        data.append({
            'time': 1600000000 + (i * 3600),
            'open': price,
            'high': price + 1,
            'low': price - 1,
            'close': price
        })
        
    df = pd.DataFrame(data)
    
    # Last candle check
    timestamp = df['time'].iloc[-1] * 1000
    
    action, reason = strategy.check_signals(df, timestamp)
    print(f"Signal 1 (Uptrend): {action} - {reason}")
    print(f"RSI: {strategy.last_rsi:.2f}")
    print(f"EMA: {strategy.last_ema:.2f}")
    
    # Verify Entry
    if action == "ENTRY_LONG":
        strategy.update_position_state(action, timestamp, strategy.last_rsi, df['close'].iloc[-1])
        print("Position state updated to LONG")
    else:
        print("Failed to trigger entry")

    # Case 2: Exit Condition
    # Close < EMA
    # Add a drop
    next_price = 50.0 # Huge drop, below EMA (~170)
    new_row = {
        'time': 1600000000 + (100 * 3600),
        'open': 199,
        'high': 199,
        'low': 50,
        'close': 50
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    timestamp = df['time'].iloc[-1] * 1000
    
    action, reason = strategy.check_signals(df, timestamp)
    print(f"Signal 2 (Drop): {action} - {reason}")
    
    if action == "EXIT_LONG":
        print("Exit triggered correctly")
    else:
        print("Failed to trigger exit")

if __name__ == "__main__":
    test_strategy()
