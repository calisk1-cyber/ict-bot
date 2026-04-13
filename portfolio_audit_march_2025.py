import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
from oanda_data import download_oanda_candles
from ict_utils import apply_ict_v18_omniscient, get_smc_bias_v11
import time

# --- SYMBOLS TO TEST (All Majors & Key Minors + XAU) ---
SYMBOLS = [
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CAD", "AUD_USD", "NZD_USD", "USD_CHF",
    "EUR_GBP", "EUR_JPY", "GBP_JPY", "XAU_USD", "AUD_JPY", "EUR_AUD", "GBP_AUD"
]

class PortfolioBacktester:
    def __init__(self, initial_balance=100000):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.active_trades = []
        self.closed_trades = []
        self.equity_curve = []
        
        # Institutional Config
        self.RISK_PER_TRADE = 0.01 # 1%
        self.COMMISSION_PER_LOT = 7.0
        self.H4_LOOKBACK = 20
        
        self.SPREADS = {
            "EUR_USD": 0.00008, "GBP_USD": 0.00012, "USD_JPY": 0.008, "USD_CAD": 0.00015,
            "AUD_USD": 0.00012, "NZD_USD": 0.00015, "USD_CHF": 0.00018, "XAU_USD": 0.35,
            "EUR_GBP": 0.00015, "EUR_JPY": 0.01, "GBP_JPY": 0.015, "AUD_JPY": 0.012,
            "EUR_AUD": 0.00018, "GBP_AUD": 0.00022
        }

    def get_pip_value(self, symbol):
        if "JPY" in symbol: return 0.01
        if "XAU" in symbol: return 0.1
        return 0.0001

    def calculate_units(self, symbol, entry, sl, risk_usd):
        dist = abs(entry - sl)
        if dist == 0: return 0
        if "XAU" in symbol: return int(risk_usd / dist)
        if "JPY" in symbol: return int(risk_usd / (dist / entry))
        return int(risk_usd / dist)

    def run(self, start_date, end_date):
        print(f"\n[PORTFOLIO AUDIT] Initializing {len(SYMBOLS)} symbols for March 2025...")
        
        all_data = {}
        global_timeline = set()
        
        for sym in SYMBOLS:
            print(f"  Fetching {sym}...")
            # M5 Data
            df_m5 = download_oanda_candles(sym, "M5", from_time=f"{start_date}T00:00:00Z", to_time=f"{end_date}T23:59:59Z")
            if df_m5.empty: continue
            df_m5 = apply_ict_v18_omniscient(df_m5)
            
            # H4 Bias (Pre-calculated for speed)
            df_h4 = download_oanda_candles(sym, "H4", from_time=f"{start_date}T00:00:00Z", to_time=f"{end_date}T23:59:59Z")
            if not df_h4.empty:
                biases = []
                for j in range(len(df_h4)):
                    window = df_h4.iloc[max(0, j-20):j+1]
                    biases.append(get_smc_bias_v11(window))
                df_h4['HTF_Bias'] = biases
                
                df_m5 = pd.merge_asof(df_m5.sort_index(), df_h4[['HTF_Bias']].sort_index(), left_index=True, right_index=True)
                df_m5['HTF_Bias'] = df_m5['HTF_Bias'].fillna("NEUTRAL")
            else:
                df_m5['HTF_Bias'] = "NEUTRAL"
                
            all_data[sym] = df_m5
            global_timeline.update(df_m5.index)
            time.sleep(1) # Rate limit protection

        sorted_timeline = sorted(list(global_timeline))
        print(f"\n[PORTFOLIO AUDIT] Starting simulation across {len(sorted_timeline)} time steps...")

        for t in sorted_timeline:
            # 1. Update Existing Trades
            self.manage_active_trades(t, all_data)
            
            # 2. Search for New Signals
            for sym, df in all_data.items():
                if t not in df.index: continue
                
                # Check if we already have a trade for this symbol
                if any(tr['symbol'] == sym for tr in self.active_trades):
                    continue
                
                row = df.loc[t]
                if not row.get('is_algo_window'): continue
                
                bias = row.get('HTF_Bias', 'NEUTRAL')
                is_bull = row.get('CISD_Bull', False) and bias == "BULLISH"
                is_bear = row.get('CISD_Bear', False) and bias == "BEARISH"
                
                if is_bull or is_bear:
                    # Signal found - execute at NEXT candle open
                    # We find the next available candle in the symbol's dataframe
                    t_idx = df.index.get_loc(t)
                    if t_idx + 1 >= len(df): continue
                    nxt = df.iloc[t_idx+1]
                    
                    spread = self.SPREADS.get(sym, 0.0002)
                    pip = self.get_pip_value(sym)
                    slip = random.uniform(0.3, 0.8) * pip
                    
                    ent = nxt['Open'] + (spread/2) + slip if is_bull else nxt['Open'] - (spread/2) - slip
                    sl_dist = 25 * pip
                    sl = ent - sl_dist if is_bull else ent + sl_dist
                    tp = ent + (ent - sl) * 2.5
                    
                    units = self.calculate_units(sym, ent, sl, self.balance * self.RISK_PER_TRADE)
                    if units > 0:
                        self.active_trades.append({
                            "symbol": sym, "side": "BUY" if is_bull else "SELL",
                            "entry": ent, "sl": sl, "tp": tp, "units": units, "open_time": nxt.name
                        })

    def manage_active_trades(self, current_time, all_data):
        remaining = []
        for tr in self.active_trades:
            sym = tr['symbol']
            df = all_data[sym]
            if current_time not in df.index:
                remaining.append(tr)
                continue
            
            row = df.loc[current_time]
            low, high = row['Low'], row['High']
            
            closed = False
            if tr['side'] == "BUY":
                if low <= tr['sl']:
                    self.close_trade(tr, tr['sl'], current_time, "SL")
                    closed = True
                elif high >= tr['tp']:
                    self.close_trade(tr, tr['tp'], current_time, "TP")
                    closed = True
            else:
                if high >= tr['sl']:
                    self.close_trade(tr, tr['sl'], current_time, "SL")
                    closed = True
                elif low <= tr['tp']:
                    self.close_trade(tr, tr['tp'], current_time, "TP")
                    closed = True
            
            if not closed: remaining.append(tr)
        self.active_trades = remaining

    def close_trade(self, tr, cp, ct, rsn):
        p_raw = (cp - tr['entry']) * tr['units'] if tr['side'] == "BUY" else (tr['entry'] - cp) * tr['units']
        p_usd = p_raw / cp if "JPY" in tr['symbol'] else p_raw
        comm = (abs(tr['units']) / 100000.0) * self.COMMISSION_PER_LOT
        net = p_usd - comm
        self.balance += net
        self.closed_trades.append({**tr, "exit": cp, "pnl": net, "exit_time": ct, "reason": rsn})

    def report(self):
        df = pd.DataFrame(self.closed_trades)
        if df.empty:
            print("No trades executed.")
            return
        
        wr = (len(df[df['pnl'] > 0]) / len(df)) * 100
        print(f"\n{'='*50}")
        print(f"   V18 PORTFOLIO AUDIT REPORT (MARCH 2025)")
        print(f"{'='*50}")
        print(f"Total Trades:     {len(df)}")
        print(f"Symbols Traded:   {df['symbol'].nunique()}")
        print(f"Win Rate:         {wr:.1f}%")
        print(f"Initial Bal:      ${self.initial_balance:.2f}")
        print(f"Final Bal:        ${self.balance:.2f}")
        print(f"Net Profit:       ${self.balance - self.initial_balance:.2f}")
        print(f"ROI:              {((self.balance-self.initial_balance)/self.initial_balance)*100:.1f}%")
        print(f"{'='*50}")
        
        # Per Symbol Stats
        print("\n[PER SYMBOL PERFORMANCE]")
        print(df.groupby('symbol')['pnl'].sum().sort_values(ascending=False))
        print(f"{'='*50}\n")

if __name__ == "__main__":
    tester = PortfolioBacktester()
    tester.run("2025-03-01", "2025-03-31")
    tester.report()
