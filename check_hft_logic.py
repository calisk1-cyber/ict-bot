import os
import sys
import pandas as pd
import pandas_ta as ta
from oanda_data import download_oanda_candles
from ict_utils import apply_ict_v12_depth, get_smc_bias_v11

SYMBOLS = ["EUR_USD", "GBP_USD", "XAU_USD", "USD_JPY", "USD_CAD"]

def check_current_hft_status():
    print("=" * 60)
    print("   HFT LOGIC AUDIT - CURRENT MARKET SCAN")
    print("=" * 60)
    
    for sym in SYMBOLS:
        print(f"\n--- {sym} ---")
        df5 = download_oanda_candles(sym, "M5", count=100)
        df1h = download_oanda_candles(sym, "H1", count=50)
        
        if df5.empty or df1h.empty:
            print("  [HATA] Veri cekilemedi."); continue
            
        bias = get_smc_bias_v11(df1h.tail(20))
        df5 = apply_ict_v12_depth(df5)
        row = df5.iloc[-1]
        price = float(row["Close"])
        
        # Scoring
        score = 0
        reasons = []
        if row.get('FVG_Bull'): score += 25; reasons.append("FVG_Bull(+25)")
        if row.get('TurtleSoup_Bull'): score += 20; reasons.append("Turtle(+20)")
        if row.get('IFVG_Bull'): score += 22; reasons.append("IFVG_Bull(+22)")
        if row.get('VI_Bull'): score += 15; reasons.append("VI_Bull(+15)")
        
        if row.get('FVG_Bear'): score -= 25; reasons.append("FVG_Bear(-25)")
        if row.get('TurtleSoup_Bear'): score -= 20; reasons.append("Turtle_Bear(-20)")
        if row.get('IFVG_Bear'): score -= 22; reasons.append("IFVG_Bear(-22)")
        if row.get('VI_Bear'): score -= 15; reasons.append("VI_Bear(-15)")
        
        # PD Array
        past_25 = df5.tail(25)
        range_high = past_25["High"].max()
        range_low  = past_25["Low"].min()
        eq = (range_high + range_low) / 2
        is_discount = price < eq
        is_premium  = price > eq
        
        print(f"  Fiyat      : {price:.5f}")
        print(f"  HTF Bias   : {bias}")
        print(f"  Aktif Skor : {score} ({', '.join(reasons) if reasons else 'Yok'})")
        print(f"  Bölge      : {'DISCOUNT' if is_discount else 'PREMIUM'} (Eq: {eq:.5f})")
        
        # Karar
        if score >= 20:
            if bias != "BULLISH": print("  [X] RET: Bias BULLISH degil.")
            elif not is_discount: print("  [X] RET: Fiyat DISCOUNT bölgesinde degil (Ucuz degil).")
            else: print("  [!] SINYAL HAZIR: BUY tetiklenebilir.")
        elif score <= -20:
            if bias != "BEARISH": print("  [X] RET: Bias BEARISH degil.")
            elif not is_premium: print("  [X] RET: Fiyat PREMIUM bölgesinde degil (Pahalı degil).")
            else: print("  [!] SINYAL HAZIR: SELL tetiklenebilir.")
        else:
            print("  [.] Beklemede: Skor Threshold (20) altinda.")

if __name__ == "__main__":
    check_current_hft_status()
