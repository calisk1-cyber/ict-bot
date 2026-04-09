import pandas as pd
import numpy as np
from oanda_data import download_oanda_candles
from ict_utils import (
    get_smc_bias_v11, apply_ict_v18_omniscient, 
    calculate_ote_v15, is_in_algorithmic_window_v18
)
from datetime import datetime, timezone

def diagnose_no_trades():
    symbols = ["EUR_USD", "GBP_USD", "XAU_USD"] # Core focus
    
    print("--- OMNISCIENT V18 DIAGNOSTIC TOOL ---")
    print(f"Current UTC Time: {datetime.now(timezone.utc)}")
    
    for symbol in symbols:
        print(f"\nAnalyzing {symbol}...")
        
        # 1. Fetch 5M data for signal scan
        df_5m = download_oanda_candles(instrument=symbol, granularity="M5", count=2000)
        # 2. Fetch 1H data for Bias
        df_1h = download_oanda_candles(instrument=symbol, granularity="H1", count=100)
        
        if df_5m.empty:
            print(f"Error: Could not fetch 5M data for {symbol}")
            continue
            
        # 3. Calculate Bias
        bias = get_smc_bias_v11(df_1h.tail(20))
        print(f"Current HTF Bias (1H): {bias}")
        
        # 4. Enrich V18 Logic
        df_v18 = apply_ict_v18_omniscient(df_5m)
        
        # 5. Scan for potential signals in the last 48 hours
        print("Scanning last 48 hours for raw signals...")
        potential_count = 0
        window_count = 0
        bias_filtered = 0
        
        recent_df = df_v18.tail(576) # ~48 hours on 5m
        
        for i in range(len(recent_df)):
            row = recent_df.iloc[i]
            ts = recent_df.index[i]
            
            if row['is_algo_window']:
                window_count += 1
                
                # Check for CISD or IDM
                is_bull = row.get('CISD_Bull') or row.get('IDM_Sweep_Bull')
                is_bear = row.get('CISD_Bear') or row.get('IDM_Sweep_Bear')
                
                if is_bull or is_bear:
                    potential_count += 1
                    
                    # Check Bias Confluence
                    if is_bull and "BULLISH" in bias:
                        print(f"Match Found: {ts} | BULLISH Signal | Bias OK")
                        bias_filtered += 1
                    elif is_bear and "BEARISH" in bias:
                        print(f"Match Found: {ts} | BEARISH Signal | Bias OK")
                        bias_filtered += 1
        
        print(f"Summary for {symbol}:")
        print(f"- Time in Algo Window: {window_count} bars")
        print(f"- Raw Signals (CISD/IDM): {potential_count}")
        print(f"- Signals Passed Bias Filter: {bias_filtered}")

if __name__ == "__main__":
    diagnose_no_trades()
