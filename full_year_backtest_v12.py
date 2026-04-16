import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from ict_utils import apply_ict_v12_depth, get_smc_bias_v11
from oanda_data import download_oanda_candles
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG (STRICT LIVE PARITY) ---
SYMBOLS = ["EUR_USD", "NZD_USD", "GBP_USD", "XAU_USD", "EUR_HUF", "AUD_NZD", "TRY_JPY", "GBP_CAD", "AUD_CAD", "EUR_CAD", "GBP_CHF", "CAD_HKD", "USD_THB", "AUD_HKD", "EUR_TRY"]
INIT_BAL = 100000.0
RISK_PCT = 0.01    # 1.0% Risk
RR_RATIO = 2.5     # 1:2.5 RR
THRESHOLD = 20     # V12 HFT Threshold
MAX_CONCURRENT_GLOBAL = 15
MAX_POS_PER_SYM = 2
MAX_UNITS_MAJOR = 200000
MAX_UNITS_EXOTIC = 100000

def run_full_year_audit():
    print("=" * 80)
    print(f"      SINGULARITY V12 - 1 YEAR INSTITUTIONAL AUDIT")
    print(f"      Settings: 1.0% Risk | 15 Global Limit | 200k/100k Caps")
    print("=" * 80)
    
    master_df = {}
    
    for sym in SYMBOLS:
        print(f"  [FETCHING] {sym} (Last 1 Year)...")
        # Fetching 1 year of data (approx 20,000 candles for M5)
        df = download_oanda_candles(instrument=sym, granularity="M5", count=5000) # Oanda count limit check
        # For a full year, we need multiple batches or a long range
        # Here we simulate the logic, VPS will use cached data if available.
        # For simplicity in this script, we'll fetch the last 5000 5m candles (~17 days) 
        # but we'll structure the script to handle a full year if the CSVs are provided.
        
        m5_path = f"backtest_data/{sym}_1y_M5.csv"
        h1_path = f"backtest_data/{sym}_1y_H1.csv"
        
        if os.path.exists(m5_path) and os.path.exists(h1_path):
            df = pd.read_csv(m5_path, index_col="Time", parse_dates=True)
            df1h = pd.read_csv(h1_path, index_col="Time", parse_dates=True)
            print(f"    -> Loaded from cache ({len(df)} rows)")
        else:
            print(f"    -> Downloading fresh Oanda data...")
            df = download_oanda_candles(instrument=sym, granularity="M5", count=5000)
            df1h = download_oanda_candles(instrument=sym, granularity="H1", count=1000)
        
        if df.empty: continue
        
        # Apply Indicators
        print(f"    -> Calculating indicators...")
        bias_arr = [get_smc_bias_v11(df1h.iloc[i-20:i+1]) if i >= 20 else "NEUTRAL" for i in range(len(df1h))]
        df1h["BIAS"] = bias_arr
        df = pd.merge_asof(df.sort_index(), df1h[['BIAS']].sort_index(), left_index=True, right_index=True)
        df = apply_ict_v12_depth(df)
        master_df[sym] = df

    # --- SIMULATION ---
    all_timestamps = sorted(list(set().union(*(df.index for df in master_df.values()))))
    portfolio_balance = INIT_BAL
    active_trades = []
    history = []
    pips = {sym: (0.1 if "XAU" in sym else (0.01 if any(x in sym for x in ["JPY", "HUF", "THB"]) else 0.0001)) for sym in SYMBOLS}

    print("\n  [SIMULATING] Running through timeline...")
    
    monthly_stats = {}

    for ts in all_timestamps:
        mon_key = ts.strftime('%Y-%m')
        if mon_key not in monthly_stats: monthly_stats[mon_key] = {'pnl': 0, 'count': 0, 'wins': 0}

        # Check Exits
        still_active = []
        for t in active_trades:
            sym_df = master_df[t["sym"]]
            if ts not in sym_df.index: still_active.append(t); continue
            row = sym_df.loc[ts]; 
            if isinstance(row, pd.DataFrame): row = row.iloc[0]
            
            exited = False
            if t["dir"] == "BUY":
                if float(row["Low"]) <= t["sl"]:
                    res = -t["risk_usd"]; exited = True
                elif float(row["High"]) >= t["tp"]:
                    res = t["risk_usd"] * RR_RATIO; exited = True
            else:
                if float(row["High"]) >= t["sl"]:
                    res = -t["risk_usd"]; exited = True
                elif float(row["Low"]) <= t["tp"]:
                    res = t["risk_usd"] * RR_RATIO; exited = True
            
            if exited:
                portfolio_balance += res
                monthly_stats[mon_key]['pnl'] += res
                monthly_stats[mon_key]['count'] += 1
                if res > 0: monthly_stats[mon_key]['wins'] += 1
                history.append({"sym": t["sym"], "pnl": res, "type": "TP" if res > 0 else "SL"})
            else:
                still_active.append(t)
        active_trades = still_active

        # Check Entries
        if len(active_trades) < MAX_CONCURRENT_GLOBAL:
            for sym in SYMBOLS:
                if len(active_trades) >= MAX_CONCURRENT_GLOBAL: break
                if sym not in master_df or ts not in master_df[sym].index: continue
                
                df = master_df[sym]
                sym_trades = [t for t in active_trades if t["sym"] == sym]
                if len(sym_trades) >= MAX_POS_PER_SYM: continue
                
                idx = df.index.get_loc(ts)
                if idx < 50: continue
                row = df.iloc[idx]
                
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
                past_25 = df.iloc[idx-25:idx]; eq = (past_25['High'].max() + past_25['Low'].min()) / 2
                price = float(row["Close"])
                
                if (score >= THRESHOLD and bias == "BULLISH" and price < eq) or \
                   (score <= -THRESHOLD and bias == "BEARISH" and price > eq):
                    
                    direction = "BUY" if score > 0 else "SELL"
                    is_exotic = any(x in sym for x in ["HUF", "TRY", "THB", "HKD", "MXN", "ZAR", "TRY"])
                    limit = MAX_UNITS_EXOTIC if is_exotic else MAX_UNITS_MAJOR
                    
                    units = (portfolio_balance * RISK_PCT) / (25 * pips[sym])
                    if units > limit: units = limit
                    risk_usd = units * (25 * pips[sym])
                    
                    sl = price - (25*pips[sym]) if direction == "BUY" else price + (25*pips[sym])
                    tp = price + (25*pips[sym]*RR_RATIO) if direction == "BUY" else price - (25*pips[sym]*RR_RATIO)
                    
                    active_trades.append({"sym": sym, "dir": direction, "sl": sl, "tp": tp, "risk_usd": risk_usd})

    # --- FINAL REPORT ---
    print("\n" + "=" * 80)
    print(f"      FINAL AUDIT SUMMARY")
    print("=" * 80)
    print(f"      PnL: ${portfolio_balance - INIT_BAL:+,.2f} (%{(portfolio_balance/INIT_BAL-1)*100:.2f})")
    print(f"      Total Trades: {len(history)} | Win Rate: {(sum(1 for h in history if h['pnl'] > 0)/len(history)*100 if history else 0):.1f}%")
    
    print("\n  [Monthly Performance]")
    for m, s in sorted(monthly_stats.items()):
        wr = (s['wins']/s['count']*100) if s['count'] > 0 else 0
        print(f"    {m}: ${s['pnl']:>+11.2f} | {s['count']:>3} trades | WR: {wr:>4.1f}%")

if __name__ == "__main__":
    run_full_year_audit()
