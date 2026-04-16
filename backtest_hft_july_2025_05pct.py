import os
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime
from ict_utils import apply_ict_v12_depth, get_smc_bias_v11
from oanda_data import download_oanda_candles

# --- CONFIG ---
SYMBOLS = ["EUR_USD", "NZD_USD", "GBP_USD", "XAU_USD", "EUR_HUF", "AUD_NZD", "TRY_JPY", "GBP_CAD", "AUD_CAD", "EUR_CAD", "GBP_CHF", "CAD_HKD", "USD_THB", "AUD_HKD", "EUR_TRY"]
DATA_DIR = "backtest_data"
INIT_BAL = 100000.0
RISK_PCT = 0.01    # Aggressive Hybrid (1.0%)
RR_RATIO = 2.5    # Following bot4_trader.py
THRESHOLD = 20    # HFT Aggressive Mode
MAX_CONCURRENT_GLOBAL = 15 # Global account limit
MAX_POS_PER_SYM = 2 # User requested max 2 per symbol
MAX_UNITS_MAJOR = 200000 # Major cap
MAX_UNITS_EXOTIC = 100000 # Exotic cap

def run_hybrid_backtest():
    print("=" * 60)
    print(f"   JULY 2025 HYBRID BACKTEST (MAX CONCURRENT: 20)")
    print(f"   Settings: Risk 0.5%, RR 1:2.5")
    print("=" * 60)
    
    print(f"[DEBUG] Current Directory: {os.getcwd()}")
    print(f"[DEBUG] Looking in: {os.path.abspath(DATA_DIR)}")
    
    if os.path.exists(DATA_DIR):
        print(f"[DEBUG] Files in {DATA_DIR}: {os.listdir(DATA_DIR)[:10]}...")
    else:
        print(f"[DEBUG] ERROR: {DATA_DIR} NOT FOUND!")

    master_df = {}
    all_timestamps = set()
    
    for sym in SYMBOLS:
        m5_path = os.path.join(DATA_DIR, f"{sym}_july_2025_M5.csv")
        h1_path = os.path.join(DATA_DIR, f"{sym}_july_2025_H1.csv")
        
        if not os.path.exists(m5_path) or not os.path.exists(h1_path): 
            print(f"  [DOWNLOADING] {sym} data from Oanda (Realistic Audit)...")
            try:
                df = download_oanda_candles(instrument=sym, granularity="M5", count=4000)
                df1h = download_oanda_candles(instrument=sym, granularity="H1", count=500)
                if df.empty or df1h.empty: 
                     print(f"  [ERROR] {sym} Oanda download failed."); continue
            except Exception as e:
                print(f"  [ERROR] {sym} fallback failed: {e}"); continue
        else:
            print(f"  [FOUND] {sym} - Loading CSV...")
            df = pd.read_csv(m5_path, index_col="Time", parse_dates=True)
            df1h = pd.read_csv(h1_path, index_col="Time", parse_dates=True)
        bias_arr = [get_smc_bias_v11(df1h.iloc[i-20:i+1]) if i >= 20 else "NEUTRAL" for i in range(len(df1h))]
        df1h["BIAS"] = bias_arr
        df = pd.merge_asof(df.sort_index(), df1h[['BIAS']].sort_index(), left_index=True, right_index=True)
        df = apply_ict_v12_depth(df)
        master_df[sym] = df
        all_timestamps.update(df.index)

    sorted_timestamps = sorted(list(all_timestamps))
    portfolio_balance = INIT_BAL
    active_trades = []
    total_trades_history = []
    pips = {sym: (0.1 if "XAU" in sym else (0.01 if any(x in sym for x in ["JPY", "HUF", "THB"]) else 0.0001)) for sym in SYMBOLS}

    for ts in sorted_timestamps:
        still_active = []
        for t in active_trades:
            sym_df = master_df[t["sym"]]
            if ts not in sym_df.index: still_active.append(t); continue
            row = sym_df.loc[ts]
            if isinstance(row, pd.DataFrame): row = row.iloc[0]
            exited = False
            if t["dir"] == "BUY":
                if float(row["Low"]) <= t["sl"]:
                    portfolio_balance -= t["risk_usd"]; total_trades_history.append({"sym": t["sym"], "type": "SL", "pnl": -t["risk_usd"]}); exited = True
                elif float(row["High"]) >= t["tp"]:
                    portfolio_balance += t["risk_usd"] * RR_RATIO; total_trades_history.append({"sym": t["sym"], "type": "TP", "pnl": t["risk_usd"] * RR_RATIO}); exited = True
            else:
                if float(row["High"]) >= t["sl"]:
                    portfolio_balance -= t["risk_usd"]; total_trades_history.append({"sym": t["sym"], "type": "SL", "pnl": -t["risk_usd"]}); exited = True
                elif float(row["Low"]) <= t["tp"]:
                    portfolio_balance += t["risk_usd"] * RR_RATIO; total_trades_history.append({"sym": t["sym"], "type": "TP", "pnl": t["risk_usd"] * RR_RATIO}); exited = True
            if not exited: still_active.append(t)
        active_trades = still_active

        if len(active_trades) < MAX_CONCURRENT_GLOBAL:
            for sym in SYMBOLS:
                if len(active_trades) >= MAX_CONCURRENT_GLOBAL: break
                sym_trades = [t for t in active_trades if t["sym"] == sym]
                if len(sym_trades) >= MAX_POS_PER_SYM: continue
                if sym not in master_df or ts not in master_df[sym].index: continue
                df = master_df[sym]; idx = df.index.get_loc(ts)
                if idx < 50: continue
                row = df.iloc[idx]; score = 0
                if row.get('FVG_Bull'): score += 25
                if row.get('TurtleSoup_Bull'): score += 20
                if row.get('IFVG_Bull'): score += 22
                if row.get('VI_Bull'): score += 15
                if row.get('FVG_Bear'): score -= 25
                if row.get('TurtleSoup_Bear'): score -= 20
                if row.get('IFVG_Bear'): score -= 22
                if row.get('VI_Bear'): score -= 15
                bias = row.get("BIAS", "NEUTRAL")
                past_25 = df.iloc[idx-25:idx]; eq = (past_25['High'].max() + past_25['Low'].min()) / 2
                price = float(row["Close"])
                # Sizing logic
                is_exotic = any(x in sym for x in ["HUF", "TRY", "THB", "HKD", "MXN", "ZAR", "TRY"])
                limit = MAX_UNITS_EXOTIC if is_exotic else MAX_UNITS_MAJOR
                
                units = (portfolio_balance * RISK_PCT) / (25 * pips[sym])
                if units > limit: units = limit
                
                risk_usd = units * (25 * pips[sym])
                
                if score >= THRESHOLD and bias == "BULLISH" and price < eq:
                    active_trades.append({"sym": sym, "dir": "BUY", "sl": price-(25*pips[sym]), "tp": price+(25*pips[sym]*RR_RATIO), "risk_usd": risk_usd})
                elif score <= -THRESHOLD and bias == "BEARISH" and price > eq:
                    active_trades.append({"sym": sym, "dir": "SELL", "sl": price+(25*pips[sym]), "tp": price-(25*pips[sym]*RR_RATIO), "risk_usd": risk_usd})

    print("\n" + "=" * 60)
    print(f"   FINAL SUMMARY (LIMIT: {MAX_CONCURRENT_GLOBAL} TOTAL, 2 PER SYM)")
    print("=" * 60)
    print(f"   Initial Balance: ${INIT_BAL:,.2f}")
    print(f"   Final Balance  : ${portfolio_balance:,.2f}")
    print(f"   Net PnL        : ${portfolio_balance - INIT_BAL:+,.2f} (%{(portfolio_balance/INIT_BAL-1)*100:.2f})")
    print(f"   Total Trades   : {len(total_trades_history)}")
    
    if total_trades_history:
        wr = (sum(1 for t in total_trades_history if t["type"] == "TP") / len(total_trades_history)) * 100
        print(f"   Win Rate       : {wr:.1f}%")
        
        # Sort by pnl
        sym_stats = {}
        for t in total_trades_history:
            s = t['sym']
            if s not in sym_stats: sym_stats[s] = {'pnl': 0, 'wins': 0, 'count': 0}
            sym_stats[s]['pnl'] += t['pnl']
            sym_stats[s]['count'] += 1
            if t['type'] == 'TP': sym_stats[s]['wins'] += 1
            
        print("\n   [Symbol Breakdown]")
        for s, st in sorted(sym_stats.items(), key=lambda x: x[1]['pnl'], reverse=True):
            print(f"   {s:<10}: {st['count']} trades | WR: {st['wins']/st['count']*100:.1f}% | PnL: ${st['pnl']:+.2f}")

if __name__ == "__main__":
    run_hybrid_backtest()
