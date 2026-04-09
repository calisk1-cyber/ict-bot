import os
import sys
import pandas as pd
import pandas_ta as ta
from oanda_data import download_oanda_candles
from ict_utils import apply_ict_v12_depth, get_smc_bias_v11

SYMBOLS = ["EUR_USD", "GBP_USD", "XAU_USD", "USD_JPY", "USD_CAD"]
TODAY_START = "2026-04-09T00:00:00Z"

def audit_today():
    print(f"--- TODAY'S TRADE AUDIT ({TODAY_START[:10]}) ---")
    
    for sym in SYMBOLS:
        print(f"\n--- {sym} Analizi ---")
        df5 = download_oanda_candles(sym, "M5", from_time=TODAY_START)
        df1h = download_oanda_candles(sym, "H1", count=100)
        
        if df5.empty:
            print("  Sinyal yok (Veri bos)."); continue
            
        # Bias
        bias = get_smc_bias_v11(df1h.tail(20))
        df5 = apply_ict_v12_depth(df5)
        
        trades_found = 0
        for i in range(25, len(df5)):
            row = df5.iloc[i]
            ts = df5.index[i]
            price = float(row["Close"])
            
            # Score
            score = 0
            reasons = []
            if row.get('FVG_Bull'): score += 25; reasons.append("FVG_Bull")
            if row.get('TurtleSoup_Bull'): score += 20; reasons.append("TurtleBull")
            if row.get('IFVG_Bull'): score += 22; reasons.append("IFVG_Bull")
            if row.get('VI_Bull'): score += 15; reasons.append("VI_Bull")
            if row.get('FVG_Bear'): score -= 25; reasons.append("FVG_Bear")
            if row.get('TurtleSoup_Bear'): score -= 20; reasons.append("TurtleBear")
            if row.get('IFVG_Bear'): score -= 22; reasons.append("IFVG_Bear")
            if row.get('VI_Bear'): score -= 15; reasons.append("VI_Bear")
            
            # PD Array
            past_25 = df5.iloc[i-25:i]
            eq = (past_25["High"].max() + past_25["Low"].min()) / 2
            
            # Entry logic
            is_buy = (score >= 20 and bias == "BULLISH" and price < eq)
            is_sell = (score <= -20 and bias == "BEARISH" and price > eq)
            
            if is_buy or is_sell:
                trades_found += 1
                dir_str = "BUY" if is_buy else "SELL"
                print(f"  [{ts}] {dir_str} | Score: {score} | Logic: {', '.join(reasons)}")
        
        if trades_found == 0:
            print("  Bu paritede bugün henüz kriterlere uygun işlem oluşmadı.")

if __name__ == "__main__":
    audit_today()
