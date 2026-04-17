import pandas as pd
import numpy as np
import random
from datetime import datetime, timezone, timedelta
from oanda_data import download_oanda_candles
from ict_utils import apply_ict_v18_omniscient, get_smc_bias_v11
import time
import os

# --- V18 PRO: INSTITUTIONAL 1-YEAR AUDIT (ULTRA-STABIL) ---
# Version: 2.1 (H4 Bias + Robust Chunking)

class FullYearInstitutionalBacktester:
    def __init__(self, initial_balance=100000):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.trades = []
        
        # Institutional Costs
        self.SPREADS = {"EUR_USD": 0.00008, "GBP_USD": 0.00012, "XAU_USD": 0.35, "USD_JPY": 0.008, "USD_CAD": 0.00015}
        self.COMMISSION_PER_LOT = 7.0 
        
        self.symbol_meta = {
            "EUR_USD": {"pip": 0.0001}, "XAU_USD": {"pip": 0.1}, "USD_JPY": {"pip": 0.01}
        }

    def calculate_units(self, ticker, entry, sl, risk_usd):
        sl_dist = abs(entry - sl)
        if sl_dist == 0: return 0
        if "XAU" in ticker:
            return int(risk_usd / sl_dist)
        elif "JPY" in ticker:
            return int(risk_usd / (sl_dist / entry))
        else:
            return int(risk_usd / sl_dist)

    def run_simulation(self, ticker, start_yr, end_yr):
        print(f"\n[AUDIT] Starting 1-Year Audit for {ticker}...")
        
        # Process monthly chunks to prevent Rate Limit / Oanda Connection issues
        current_date = datetime(2025, 1, 1)
        final_date = datetime(2025, 12, 31)
        
        while current_date < final_date:
            month_end = current_date + timedelta(days=32)
            month_end = month_end.replace(day=1) - timedelta(seconds=1)
            if month_end > final_date: month_end = final_date
            
            s_str = current_date.strftime("%Y-%m-%d")
            e_str = month_end.strftime("%Y-%m-%d")
            
            print(f"  --> Chunk: {s_str} to {e_str}")
            self.process_chunk(ticker, s_str, e_str)
            
            current_date = month_end + timedelta(seconds=1)
            time.sleep(2) # Breath for Oanda

    def process_chunk(self, ticker, s_str, e_str):
        try:
            # 1. Fetch M5 Data
            df = download_oanda_candles(ticker, "M5", from_time=f"{s_str}T00:00:00Z", to_time=f"{e_str}T23:59:59Z")
            if df.empty: return
            
            df = apply_ict_v18_omniscient(df)
            
            # 2. Fetch H4 Data for Bias
            df_h4 = download_oanda_candles(ticker, "H4", from_time=f"{s_str}T00:00:00Z", to_time=f"{e_str}T23:59:59Z")
            
            # 3. Handle Bias Mapping
            if not df_h4.empty:
                h4_biases = []
                for j in range(len(df_h4)):
                    window = df_h4.iloc[max(0, j-20):j+1]
                    h4_biases.append(str(get_smc_bias_v11(window)))
                df_h4['calculated_bias'] = h4_biases
                
                # Careful Merge
                df = df.sort_index()
                df_h4 = df_h4.sort_index()
                df = pd.merge_asof(df, df_h4[['calculated_bias']], left_index=True, right_index=True, direction='backward')
                df.rename(columns={'calculated_bias': 'HTF_Bias'}, inplace=True)
                df['HTF_Bias'] = df['HTF_Bias'].fillna("NEUTRAL")
            else:
                df['HTF_Bias'] = "NEUTRAL"

            # 4. Step through M5 candles
            active_trade = None
            spread = self.SPREADS.get(ticker, 0.0001)
            meta = self.symbol_meta[ticker]
            
            for i in range(len(df)-1):
                row = df.iloc[i]
                nxt = df.iloc[i+1]
                
                if active_trade:
                    if active_trade['side'] == "BUY":
                        if nxt['Low'] <= active_trade['sl']:
                            self.close_trade(active_trade, active_trade['sl'], "SL")
                            active_trade = None
                        elif nxt['High'] >= active_trade['tp']:
                            self.close_trade(active_trade, active_trade['tp'], "TP")
                            active_trade = None
                    else:
                        if nxt['High'] >= active_trade['sl']:
                            self.close_trade(active_trade, active_trade['sl'], "SL")
                            active_trade = None
                        elif nxt['Low'] <= active_trade['tp']:
                            self.close_trade(active_trade, active_trade['tp'], "TP")
                            active_trade = None
                    continue

                if not row.get('is_algo_window'): continue
                
                bias = str(row.get('HTF_Bias', 'NEUTRAL'))
                is_bull = row.get('CISD_Bull', False) and bias == "BULLISH"
                is_bear = row.get('CISD_Bear', False) and bias == "BEARISH"
                
                if is_bull or is_bear:
                    slip = random.uniform(0.3, 0.7) * meta['pip']
                    ent = nxt['Open'] + (spread/2) + slip if is_bull else nxt['Open'] - (spread/2) - slip
                    
                    sl_dist = 25 * meta['pip']
                    sl = ent - sl_dist if is_bull else ent + sl_dist
                    tp = ent + (ent - sl) * 2.5
                    
                    u = self.calculate_units(ticker, ent, sl, self.balance * 0.01)
                    if u > 0:
                        active_trade = {"symbol": ticker, "side": "BUY" if is_bull else "SELL", "entry": ent, "sl": sl, "tp": tp, "units": u}
        except Exception as e:
            print(f"  [ERROR] Chunk {s_str} failed: {e}")

    def close_trade(self, trade, cp, rsn):
        p_raw = (cp - trade['entry']) * trade['units'] if trade['side'] == "BUY" else (trade['entry'] - cp) * trade['units']
        p_usd = p_raw / cp if "JPY" in trade['symbol'] else p_raw
        comm = (abs(trade['units']) / 100000.0) * self.COMMISSION_PER_LOT
        self.balance += (p_usd - comm)
        self.trades.append({"symbol": trade['symbol'], "pnl": p_usd - comm})

    def report(self):
        dt = pd.DataFrame(self.trades)
        if dt.empty:
            print("No trades found.")
            return
        wr = (len(dt[dt['pnl'] > 0]) / len(dt)) * 100
        print(f"\n{'='*50}\n  V18 INSTITUTIONAL 2025 AUDIT REPORT\n{'='*50}")
        print(f"Total Trades: {len(dt)}\nWin Rate:     {wr:.1f}%\nNet PnL:      ${self.balance - self.initial_balance:.2f}\nFinal Bal:    ${self.balance:.2f}\n{'='*50}\n")

if __name__ == "__main__":
    t = FullYearInstitutionalBacktester()
    for s in ["EUR_USD", "XAU_USD", "USD_JPY"]:
        t.run_simulation(s, 2025, 2025)
    t.report()
