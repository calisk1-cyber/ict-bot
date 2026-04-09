import os
import sys
import pandas as pd
import pandas_ta as ta
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from oanda_data import download_oanda_candles
from ict_utils import apply_ict_v12_depth, get_smc_bias_v11

# --- KURUMSAL AYARLAR ---
TRADE_SYMBOLS = ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "XAU_USD"]
FROM_5M = "2025-06-01T00:00:00Z"
TO_5M   = "2025-06-30T23:59:00Z"

INIT_BAL = 100000.0
SPREADS = {"EUR_USD": 0.00012, "GBP_USD": 0.00015, "USD_JPY": 0.015, "USD_CAD": 0.00015, "XAU_USD": 0.25}
# Oanda Standard Commission: $3.5 per lot (100k) side -> $7 round trip
COMMISSION_PER_LOT = 7.0 

def run_institutional_audit_fixed():
    print("=" * 60)
    print("   INSTITUTIONAL AUDIT (FEES & CURRENCY FIXED)")
    print(f"   Month: June 2025 | Balance: ${INIT_BAL}")
    print("=" * 60)
    
    grand_net = 0.0
    grand_total = 0
    grand_wins = 0
    
    for sym in TRADE_SYMBOLS:
        print(f"\n--- {sym} Denetleniyor ---")
        df5 = download_oanda_candles(sym, "M5", from_time=FROM_5M, to_time=TO_5M)
        df1h = download_oanda_candles(sym, "H1", from_time="2025-05-01T00:00:00Z", to_time=TO_5M)
        if df5.empty or df1h.empty: continue

        bias_arr = [get_smc_bias_v11(df1h.iloc[:i+1].tail(20)) if i>=20 else "NEUTRAL" for i in range(len(df1h))]
        df1h["BIAS"] = bias_arr
        df_merged = pd.merge_asof(df5.sort_index(), df1h[['BIAS']].sort_index(), left_index=True, right_index=True)
        df_merged = apply_ict_v12_depth(df_merged)
        df_merged['ATR'] = ta.atr(df_merged['High'], df_merged['Low'], df_merged['Close'], length=14)
        
        balance = INIT_BAL; active = None; sym_trades = []
        spread = SPREADS.get(sym, 0.00015)
        
        for i in range(50, len(df_merged) - 1):
            row = df_merged.iloc[i]; price = float(row["Close"]); ts = df_merged.index[i]
            
            if active:
                t = active
                hit_sl = (t["dir"] == "BUY" and row["Low"] <= t["sl"]) or (t["dir"] == "SELL" and row["High"] >= t["sl"])
                hit_tp = (t["dir"] == "BUY" and row["High"] >= t["tp"]) or (t["dir"] == "SELL" and row["Low"] <= t["tp"])
                
                if hit_sl or hit_tp:
                    exit_p = t["sl"] if hit_sl else t["tp"]
                    raw_diff = (exit_p - t["entry"]) if t["dir"] == "BUY" else (t["entry"] - exit_p)
                    
                    # PnL Calculation based on pair type
                    if "JPY" in sym:
                        pnl_usd = (raw_diff * t["units"]) / price # Convert JPY to USD approx
                    elif "CAD" in sym:
                        pnl_usd = (raw_diff * t["units"]) / 1.35 # Approx USDCAD rate
                    elif "XAU" in sym:
                        pnl_usd = (raw_diff * t["units"]) # Gold is already USD
                    else:
                        pnl_usd = (raw_diff * t["units"]) 
                    
                    net_pnl = pnl_usd - t["cost"]
                    balance += net_pnl
                    sym_trades.append(("TP" if hit_tp else "SL", ts, net_pnl))
                    active = None
                continue
                
            score = 0
            if row.get('FVG_Bull'): score += 25
            if row.get('TurtleSoup_Bull'): score += 20
            if row.get('IFVG_Bull'): score += 22
            if row.get('VI_Bull'): score += 15
            if row.get('FVG_Bear'): score -= 25
            if row.get('TurtleSoup_Bear'): score -= 20
            if row.get('IFVG_Bear'): score -= 22
            if row.get('VI_Bear'): score -= 15
            
            bias = row.get("BIAS", "NEUTRAL"); atr = float(row.get("ATR", price*0.001))
            if pd.isna(atr): atr = price*0.001
            
            eq = (df_merged.iloc[i-25:i]['High'].max() + df_merged.iloc[i-25:i]['Low'].min()) / 2
            
            if (score >= 20 and bias == "BULLISH" and price < eq) or (score <= -20 and bias == "BEARISH" and price > eq):
                direction = "BUY" if score > 0 else "SELL"
                sl_dist = atr * 1.5
                sl = price - sl_dist if direction == "BUY" else price + sl_dist
                tp = price + (sl_dist * 1.5) if direction == "BUY" else price - (sl_dist * 1.5)
                
                # Risk %1
                risk_amt = balance * 0.01
                if "JPY" in sym: units = (risk_amt * price) / sl_dist # Risk in JPY units
                else: units = risk_amt / sl_dist
                
                # Fees
                spread_cost = (spread * units) / (price if "JPY" in sym or "CAD" in sym else 1.0)
                comm_cost = (units / 100000) * COMMISSION_PER_LOT
                active = {"dir": direction, "entry": price, "sl": sl, "tp": tp, "units": units, "cost": spread_cost + comm_cost}
                
        if sym_trades:
            net = sum(t[2] for t in sym_trades); wins = sum(1 for t in sym_trades if t[0] == "TP")
            grand_net += net; grand_total += len(sym_trades); grand_wins += wins
            print(f"  Islem: {len(sym_trades)} | Net: ${net:+.2f}")

    print("\n" + "=" * 60)
    print(f"  INSTITUTIONAL AUDIT FINAL (NET OF ALL FEES)")
    print(f"  Total Trades : {grand_total}")
    print(f"  Win Rate     : {grand_wins/grand_total*100:.1f}%")
    print(f"  Total Net    : ${grand_net:+.2f}")
    print("=" * 60)

if __name__ == "__main__":
    run_institutional_audit_fixed()
