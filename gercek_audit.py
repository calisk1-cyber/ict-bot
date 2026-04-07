import re
import math
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime, timedelta
from collections import defaultdict
import os
from dotenv import load_dotenv
import sys

# Windows console encoding fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# Load credentials
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"))

try:
    import oandapyV20
    from oandapyV20 import API
    from oandapyV20.endpoints.instruments import InstrumentsCandles
    OANDA_OK = True
except ImportError:
    OANDA_OK = False
    print("[WARN] oandapyV20 not found, using fallback table for costs.")

# ============================================================
# SETTINGS
# ============================================================
API_KEY     = os.getenv("OANDA_API_KEY", "4e11a694872451e5527d26b1a70a5d59-31a2af28be2747a58fe4e900e0e878ae")
ACCOUNT_ID  = os.getenv("OANDA_ACCOUNT_ID", "101-001-38879647-001")
ENVIRONMENT = os.getenv("OANDA_ENV", "practice")
LOG_FILE    = r"C:\Users\LENOVO\Desktop\bot\master_1000_portfolio_log.txt"
START_BALANCE = 100_000.0

BROKER_COSTS = {
    "EUR_USD": (1.2, 3.50, 0.3), "GBP_USD": (1.8, 3.50, 0.5),
    "XAU_USD": (25.0, 0.00, 1.5), "NAS100_USD": (150.0, 0.00, 8.0),
}
PIP_VALUE = {
    "EUR_USD": 10.0, "GBP_USD": 10.0, "XAU_USD": 1.0, "NAS100_USD": 1.0,
}

def fetch_real_spread(instrument, api_key, environment):
    if not OANDA_OK: return None
    try:
        client = API(access_token=api_key, environment=environment)
        params = {"count": 100, "granularity": "M5", "price": "BA"}
        r = InstrumentsCandles(instrument=instrument, params=params)
        client.request(r)
        spreads = [float(c["ask"]["c"]) - float(c["bid"]["c"]) for c in r.response["candles"] if c["complete"]]
        if spreads:
            avg_spread = np.mean(spreads)
            print(f"  [OK] {instrument}: Avg Spread = {avg_spread:.6f}")
            return avg_spread
        return None
    except Exception as e:
        print(f"  [WARN] {instrument} spread fetch failed: {e}")
        return None

def parse_log(filepath):
    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[+\-\d:]*)"
        r"\s*\|\s*(\w+)"
        r"\s*\|\s*(LONG|SHORT)"
        r"\s*\|\s*PnL:\s*([\-\d\.]+)"
        r"\s*\|\s*(SL|TP|OPEN)"
    )
    trades = []
    if not os.path.exists(filepath): return pd.DataFrame()
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                trades.append({
                    "time": m.group(1).strip(), "instrument": m.group(2).strip(),
                    "direction": m.group(3).strip(), "raw_pnl": float(m.group(4)),
                    "outcome": m.group(5).strip(),
                })
    return pd.DataFrame(trades)

def compute_real_cost(instrument, raw_pnl, outcome, real_spreads):
    pip_val = PIP_VALUE.get(instrument, 1.0)
    fallback = BROKER_COSTS.get(instrument, (2.0, 3.50, 0.5))
    if instrument in real_spreads and real_spreads[instrument] is not None:
        spread_pips = real_spreads[instrument] / (0.0001 if "USD" in instrument and "XAU" not in instrument and "NAS" not in instrument else 1.0)
    else: spread_pips = fallback[0]
    sl_pips_est = 15.0 if "USD" in instrument and "XAU" not in instrument and "NAS" not in instrument else (150.0 if "XAU" in instrument else 500.0)
    approx_lots = abs(raw_pnl) / (sl_pips_est * pip_val) if outcome == "SL" else abs(raw_pnl) / (sl_pips_est * 3 * pip_val)
    approx_lots = max(approx_lots, 0.01)
    spread_cost = spread_pips * pip_val * approx_lots
    slippage_cost = fallback[2] * (1.5 if outcome == "SL" else 1.0) * pip_val * approx_lots
    commission_cost = fallback[1] * approx_lots * 2
    return spread_cost + slippage_cost + commission_cost, spread_cost, slippage_cost, commission_cost

def run_audit(trades_df, real_spreads):
    balance_orig = balance_real = START_BALANCE
    equity_orig, equity_real = [START_BALANCE], [START_BALANCE]
    results = []
    for _, row in trades_df.iterrows():
        if row["outcome"] == "OPEN": continue
        cost, s_c, sl_c, c_c = compute_real_cost(row["instrument"], row["raw_pnl"], row["outcome"], real_spreads)
        real_pnl = row["raw_pnl"] - cost
        balance_orig += row["raw_pnl"]; balance_real += real_pnl
        equity_orig.append(balance_orig); equity_real.append(balance_real)
        results.append({
            "time": row["time"], "instrument": row["instrument"], "raw_pnl": row["raw_pnl"], "total_cost": cost,
            "real_pnl": real_pnl, "bal_orig": balance_orig, "bal_real": balance_real,
            "spread_cost": s_c, "slip_cost": sl_c, "comm_cost": c_c
        })
    return pd.DataFrame(results), equity_orig, equity_real

def compute_metrics(results_df, equity, label):
    closed = results_df.copy()
    pnl_col = "real_pnl" if label == "Gerçekçi" else "raw_pnl"
    wins, losses = closed[closed[pnl_col] > 0], closed[closed[pnl_col] <= 0]
    win_rate = len(wins) / len(closed) * 100 if len(closed) else 0
    net_pnl = equity[-1] - START_BALANCE
    eq = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / (peak + 1e-9) * 100
    max_dd = abs(dd.min())
    sharpe = (closed[pnl_col].mean() / (closed[pnl_col].std() + 1e-9)) * np.sqrt(252)
    return {"Win Rate (%)": round(win_rate, 2), "Net PnL ($)": round(net_pnl, 2), "Max DD (%)": round(max_dd, 2), "Sharpe": round(sharpe, 2)}

def plot_dashboard(results_df, equity_orig, equity_real, m_o, m_r):
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(15, 10))
    ax1 = fig.add_subplot(2, 1, 1)
    ax1.plot(equity_orig, color='orange', label='Theoretical (0 Cost)')
    ax1.plot(equity_real, color='lime', label='Realistic (Broker Costs)')
    ax1.set_title("Equity Curve: Institutional Realworld Audit")
    ax1.legend(); ax1.grid(alpha=0.2)
    print("\n[OK] Dashboard Saved to: audit_raporu.png")
    plt.savefig("audit_raporu.png", dpi=150)

def main():
    print("--- REALISTIC INSTITUTIONAL AUDIT ENGINE ---")
    trades_df = parse_log(LOG_FILE)
    if trades_df.empty:
        print("[ERROR] Log file not found or empty.")
        return
    real_spreads = {instr: fetch_real_spread(instr, API_KEY, ENVIRONMENT) for instr in trades_df["instrument"].unique()}
    results_df, eq_o, eq_r = run_audit(trades_df, real_spreads)
    m_o, m_r = compute_metrics(results_df, eq_o, "Org"), compute_metrics(results_df, eq_r, "Real")
    print("\n" + "="*40); print(f"{'METRIC':<15} {'ORIGINAL':>10} {'REALISTIC':>10}")
    for k in m_o: print(f"{k:<15} {str(m_o[k]):>10} {str(m_r[k]):>10}")
    plot_dashboard(results_df, eq_o, eq_r, m_o, m_r)

if __name__ == "__main__": main()
