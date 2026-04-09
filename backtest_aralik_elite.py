import os
import sys
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from oanda_data import download_oanda_candles
from ict_utils import apply_ict_v18_omniscient, calculate_ote_v15, get_smc_bias_v11

# --- AYARLAR ---
TRADE_SYMBOLS = ["USD_JPY", "XAU_USD", "USD_CAD"]
CORR_MAP = {"XAU_USD": "EUR_USD", "USD_JPY": "USD_CAD", "USD_CAD": "USD_JPY"}

FROM_5M = "2024-12-01T00:00:00Z"
TO_5M   = "2024-12-31T23:59:00Z"
FROM_1H = "2024-11-01T00:00:00Z"

INIT_BAL = 100000.0  # Kurumsal bakiye
RISK_PCT = 0.01      # %1 Risk

def run_elite_backtest():
    print("=" * 60)
    print("   ARALIK 2024 - V18.5 ULTIMATE PRECISION (ELITE TRIO)")
    print("=" * 60)
    
    grand_net = 0.0
    grand_total = 0
    grand_wins = 0
    all_trades = []
    
    for sym in TRADE_SYMBOLS:
        print(f"\n--- {sym} Denetleniyor ---")
        
        # 1. Veri Cekimi
        df5 = download_oanda_candles(sym, "M5", from_time=FROM_5M, to_time=TO_5M)
        dfH = download_oanda_candles(sym, "H1", from_time=FROM_1H, to_time=TO_5M)
        
        corr_sym = CORR_MAP.get(sym)
        df5_corr = download_oanda_candles(corr_sym, "M5", from_time=FROM_5M, to_time=TO_5M) if corr_sym else pd.DataFrame()
        
        if df5.empty or dfH.empty:
            print("  [HATA] Yeterli veri yok."); continue
            
        # 2. Indikatorler
        df5["EMA9"]    = ta.ema(df5["Close"], length=9)
        df5["EMA21"]   = ta.ema(df5["Close"], length=21)
        df5["EMA200"]  = ta.ema(df5["Close"], length=200)
        df5["ATR"]     = ta.atr(df5["High"], df5["Low"], df5["Close"], length=14)
        df5["RSI"]     = ta.rsi(df5["Close"], length=14)
        df5["VOL_SMA"] = ta.sma(df5["Volume"], length=20)
        
        dfH["EMA200"]  = ta.ema(dfH["Close"], length=200)
        
        # SMT / ICT Enrichment
        print("  ICT Algoritmalari calistiriliyor...")
        df_v18 = apply_ict_v18_omniscient(df5.copy(), df5_corr.copy() if not df5_corr.empty else None)
        
        # 1H Bias tablosu 
        print("  HTF Bias (1H) isleniyor...")
        # Optimize Bias calculation: pre-calculate step by step to avoid huge O(N^2)
        bias_arr = []
        for i in range(len(dfH)):
            if i < 20: bias_arr.append("NEUTRAL")
            else: bias_arr.append(get_smc_bias_v11(dfH.iloc[i-20:i+1]))
        dfH["BIAS"] = bias_arr
        
        # Merge Bias to 5m timeframe
        df_merged = pd.merge_asof(df_v18.sort_index(), dfH[['BIAS']].sort_index(), left_index=True, right_index=True)
        
        balance = INIT_BAL
        active = None
        sym_trades = []
        
        print("  Pusu takibi ve Simulator basliyor...")
        for i in range(50, len(df_merged) - 1):
            ts   = df_merged.index[i]
            row  = df_merged.iloc[i]
            price = float(row["Close"])
            
            # EXIT 
            if active:
                t = active
                if t["dir"] == "BUY":
                    if row["Low"] <= t["sl"]:
                        loss = balance * RISK_PCT
                        balance -= loss
                        sym_trades.append(("SL", ts, -loss))
                        active = None
                    elif row["High"] >= t["tp"]:
                        gain = (balance * RISK_PCT) * 3.0 # TP RR = 3.0 in this precision
                        balance += gain
                        sym_trades.append(("TP", ts, gain))
                        active = None
                else: # SELL
                    if row["High"] >= t["sl"]:
                        loss = balance * RISK_PCT
                        balance -= loss
                        sym_trades.append(("SL", ts, -loss))
                        active = None
                    elif row["Low"] <= t["tp"]:
                        gain = (balance * RISK_PCT) * 3.0
                        balance += gain
                        sym_trades.append(("TP", ts, gain))
                        active = None
                continue
                
            # ENTRY SIGNS
            vol_sma = float(row.get("VOL_SMA", 0))
            if pd.isna(vol_sma) or float(row["Volume"]) < (vol_sma * 1.5): continue
            
            atr  = float(row.get("ATR", price*0.001))
            bias = row.get("BIAS", "NEUTRAL")
            
            ema9  = float(row.get("EMA9", 0))
            ema21 = float(row.get("EMA21", 0))
            
            # PD Array 
            start_idx = max(0, i-25)
            past_25 = df_merged.iloc[start_idx:i]
            range_high = past_25["High"].max()
            range_low  = past_25["Low"].min()
            eq = (range_high + range_low) / 2
            is_discount = price < eq
            is_premium  = price > eq
            
            # CISD
            cisd_bull = row.get("CISD_Bull", False)
            cisd_bear = row.get("CISD_Bear", False)
            
            setup_bull = cisd_bull and bias == "BULLISH" and ema9 > ema21 and is_discount
            setup_bear = cisd_bear and bias == "BEARISH" and ema9 < ema21 and is_premium
            
            if not (setup_bull or setup_bear): continue
            
            # Giris Kosullari (AI/VIX haric)
            direction = "BUY" if setup_bull else "SELL"
            
            # OTE + Dynamic Risk
            past_15 = df_merged.iloc[max(0, i-15):i]
            ote_target = calculate_ote_v15(past_15["High"].max(), past_15["Low"].min(), direction)
            
            sl_dist = atr * 1.5
            sl = ote_target - sl_dist if direction == "BUY" else ote_target + sl_dist
            tp = ote_target + (sl_dist * 3.0) if direction == "BUY" else ote_target - (sl_dist * 3.0)
            
            active = {"dir": direction, "ote": ote_target, "sl": sl, "tp": tp, "entry_ts": ts}
            
        # PNL Rapor 
        if sym_trades:
            wins = sum(1 for t in sym_trades if t[0] == "TP")
            net  = balance - INIT_BAL
            wr   = wins / len(sym_trades) * 100
            print(f"  Islem    : {len(sym_trades)}")
            print(f"  Kazanan  : {wins} | Kaybeden: {len(sym_trades)-wins}")
            print(f"  Win Rate : {wr:.1f}%")
            print(f"  Net PnL  : ${net:+.2f}")
            grand_net   += net
            grand_total += len(sym_trades)
            grand_wins  += wins
            all_trades.extend(sym_trades)
        else:
            print("  Islem acilmadi. Bu cok secici (Precision) sistemin ozelligi.")

    print("\n" + "=" * 60)
    print("  GENEL SONUC - ULTIMATE PRECISION (ARALIK 2024)")
    print("=" * 60)
    print(f"  Toplam Islem : {grand_total}")
    if grand_total > 0:
        print(f"  Kazananlar   : {grand_wins}")
        print(f"  Kaybedenler  : {grand_total - grand_wins}")
        print(f"  Genel WR     : {grand_wins/grand_total*100:.1f}%")
    print(f"  Toplam Net   : ${grand_net:+.2f}")
    print("=" * 60)

if __name__ == "__main__":
    run_elite_backtest()
