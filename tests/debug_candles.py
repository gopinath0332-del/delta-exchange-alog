import os
import sys
import time
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.rest_client import DeltaRestClient
from core.config import Config

def debug_candles():
    print("Fetching last 5 candles for XRPUSD...")
    config = Config()
    client = DeltaRestClient(config)
    
    # Check symbol first
    products = client.get_products()
    xrp_products = [p['symbol'] for p in products if 'XRP' in p['symbol']]
    print(f"Available XRP symbols: {xrp_products[:10]}")
    
    end_time = int(time.time())
    start_time = end_time - (10 * 24 * 3600) # 10 days for EMA 50 warmup
    
    response = client._make_direct_request(
        "/v2/history/candles", 
        params={
            "resolution": "1h",
            "symbol": "XRPUSD", # Changed from XRP-USD
            "start": start_time,
            "end": end_time
        }
    )
    
    candles = response.get("result", [])
    df = pd.DataFrame(candles)
    
    if df.empty:
        print("No candles found!")
        return
        
    # Sort
    if 'time' in df.columns:
        if df['time'].iloc[0] > df['time'].iloc[-1]:
            df = df.iloc[::-1].reset_index(drop=True)
            
    # --- Reproduce HA Logic ---
    o = df['open'].astype(float)
    h = df['high'].astype(float)
    l = df['low'].astype(float)
    c = df['close'].astype(float)
    
    df_ha = df.copy()
    df_ha['close'] = (o + h + l + c) / 4.0
    
    ha_open_list = [0.0] * len(df)
    ha_close_list = df_ha['close'].values
    ha_open_list[0] = (o.iloc[0] + c.iloc[0]) / 2.0
    
    for i in range(1, len(df)):
        ha_open_list[i] = (ha_open_list[i-1] + ha_close_list[i-1]) / 2.0
        
    df_ha['open'] = ha_open_list
    df_ha['high'] = df_ha[['high', 'open', 'close']].max(axis=1)
    df_ha['low'] = df_ha[['low', 'open', 'close']].min(axis=1)
    
    # --- Calc EMA ---
    import ta
    ema_series = ta.trend.ema_indicator(df_ha['close'], window=50)
    
    print("\nLast 5 Candles (Heikin Ashi):")
    for i in range(len(df_ha)-5, len(df_ha)):
        if i < 0: continue
        row = df_ha.iloc[i]
        ts = row['time']
        date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        
        close_val = row['close']
        ema_val = ema_series.iloc[i]
        
        signal = ""
        if close_val < ema_val:
            signal = " [EXIT LONG Condition MET]"
        else:
            signal = " [No Exit]"
            
        print(f"Index {i}: {date_str} (TS: {ts}) | HA_Close: {close_val:.4f} | EMA_50: {ema_val:.4f} {signal}")

    print(f"\nCurrent System Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    debug_candles()
