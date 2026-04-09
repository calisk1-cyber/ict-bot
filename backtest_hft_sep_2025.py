import os
import sys
import pandas as pd
import pandas_ta as ta
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from oanda_data import download_oanda_candles
from ict_utils import apply_ict_v12_depth, get_smc_bias_v11

# --- AYARLAR ---
TRADE_SYMBOLS = ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "XAU_USD"]
FROM_5M = "2025-09-01T00:00:00Z"
TO_5M   = "2025-09-30T23:59:00Z"

INIT_BAL = 100000.0  # 100k Dolar
THRESHOLD = 20       # Agresif Score!
RR_RATIO = 1.5       # Agresif HFT Scalp RR

def run_hft_backtest_sep():
    print("=" * 60)
    print(f"   EYLUL 2025 - HFT AGGRESSIVE MODE ($100,000 BUDGET)")
    print("=" * 60)
    
    grand_net = 0.0
    grand_total = 0
    grand_wins = 0
    
    for sym in TRADE_SYMBOLS:
        print(f"\n--- {sym} Denetleniyor ---")
        df5 = download_oanda_candles(sym, "M5", from_time=FROM_5M, to_time=TO_5M)
        df1h = download_oanda_candles(sym, "H1", from_time="2025-08-01T00:00:00Z", to_time=TO_5M)
        
        if df5.empty or df1h.empty:
            print(f"  [UYARI] {sym} icin veri bulunamadi."); continue

        # Bias Pre-calc
        bias_arr = []
        for i in range(len(df1h)):
            if i < 20: bias_arr.append("NEUTRAL")
            else: bias_arr.append(get_smc_bias_v11(df1h.iloc[i-20:i+1]))
        df1h["BIAS"] = bias_arr
        
        df_merged = pd.merge_asof(df5.sort_index(), df1h[['BIAS']].sort_index(), left_index=True, right_index=True)
        
        # Enrichment
        try:
            df_merged = apply_ict_v12_depth(df_merged)
        except Exception as e:
            print(f"Hata indicators: {e}")
            continue
            
        df_merged['ATR'] = ta.atr(df_merged['High'], df_merged['Low'], df_merged['Close'], length=14)
        
        balance = INIT_BAL
        active = None
        sym_trades = []
        
        for i in range(50, len(df_merged) - 1):
            ts   = df_merged.index[i]
            row  = df_merged.iloc[i]
            price = float(row["Close"])
            
            # --- EXIT ---
            if active:
                t = active
                if t["dir"] == "BUY":
                    if row["Low"] <= t["sl"]:
                        loss = balance * 0.01
                        balance -= loss
                        sym_trades.append(("SL", ts, -loss))
                        active = None
                    elif row["High"] >= t["tp"]:
                        gain = (balance * 0.01) * RR_RATIO
                        balance += gain
                        sym_trades.append(("TP", ts, gain))
                        active = None
                else: 
                    if row["High"] >= t["sl"]:
                        loss = balance * 0.01
                        balance -= loss
                        sym_trades.append(("SL", ts, -loss))
                        active = None
                    elif row["Low"] <= t["tp"]:
                        gain = (balance * 0.01) * RR_RATIO
                        balance += gain
                        sym_trades.append(("TP", ts, gain))
                        active = None
                continue
                
            # --- SIGNAL ---
            score = 0
            if row.get('FVG_Bull'): score += 25
            if row.get('TurtleSoup_Bull'): score += 20
            if row.get('IFVG_Bull'): score += 22
            if row.get('VI_Bull'): score += 15
            
            if row.get('FVG_Bear'): score -= 25
            if row.get('TurtleSoup_Bear'): score -= 20
            if row.get('IFVG_Bear'): score -= 22
            if row.get('VI_Bear'): score -= 15
            
            bias = row.get("BIAS", "NEUTRAL")
            atr = float(row.get("ATR", price*0.001))
            if pd.isna(atr): atr = price*0.001
            
            # PD Array
            past_25 = df_merged.iloc[max(0, i-25):i]
            if len(past_25) > 0:
                eq = (past_25['High'].max() + past_25['Low'].min()) / 2
            else:
                eq = price
            
            # ENTRY (HFT Modu: PD Array + Score + Bias)
            if score >= THRESHOLD and bias == "BULLISH" and price < eq:
                sl_dist = atr * 1.5
                sl = price - sl_dist
                tp = price + (sl_dist * RR_RATIO)
                active = {"dir": "BUY", "sl": sl, "tp": tp}
            elif score <= -THRESHOLD and bias == "BEARISH" and price > eq:
                sl_dist = atr * 1.5
                sl = price + sl_dist
                tp = price - (sl_dist * RR_RATIO)
                active = {"dir": "SELL", "sl": sl, "tp": tp}
                
        # Rapor
        if sym_trades:
            wins = sum(1 for t in sym_trades if t[0] == "TP")
            net  = balance - INIT_BAL
            wr   = (wins / len(sym_trades) * 100) if len(sym_trades) > 0 else 0
            print(f"  Islem    : {len(sym_trades)}")
            print(f"  Net PnL  : ${net:+.2f} (WR: {wr:.1f}%)")
            grand_net   += net
            grand_total += len(sym_trades)
            grand_wins  += wins
        else:
            print("  Islem yok.")

    print("\n" + "=" * 60)
    print(f"  GENEL SONUC - EYLUL 2025 ($100k Bakiye)")
    print("=" * 60)
    print(f"  Toplam Islem : {grand_total}")
    if grand_total > 0:
        print(f"  Kazananlar   : {grand_wins}")
        print(f"  Genel WR     : {grand_wins/grand_total*100:.1f}%")
    print(f"  Toplam Net   : ${grand_net:+.2f}")
    print("=" * 60)

if __name__ == "__main__":
    run_hft_backtest_sep()
