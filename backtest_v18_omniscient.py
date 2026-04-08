import pandas as pd
import numpy as np
import os
import yfinance as yf
from datetime import datetime
from ict_utils import (
    download_full_history, get_smc_bias_v11, apply_ict_v18_omniscient, 
    calculate_ote_v15
)

class OmniscientBacktester:
    def __init__(self):
        self.balance = 1000.0
        self.initial_balance = 1000.0
        self.trades = []

    def run(self, pair1="EUR_USD", pair2="GBP_USD", period="30d"):
        print(f"Executing V18 OMNISCIENT High-Frequency Audit for {pair1}...")
        
        df_main_1h = download_full_history(pair1, interval="1h", period="60d")
        df_main_5m = download_full_history(pair1, interval="5m", period=period)
        df_corr_5m = download_full_history(pair2, interval="5m", period=period)
        
        if df_main_5m.empty: return
        
        df_v18 = apply_ict_v18_omniscient(df_main_5m, df_corr_5m)
        
        df_main_1h['HTF_Bias'] = [get_smc_bias_v11(df_main_1h.iloc[:i+1].tail(20)) for i in range(len(df_main_1h))]
        df_v18 = pd.merge_asof(df_v18.sort_index(), df_main_1h[['HTF_Bias']].sort_index(), left_index=True, right_index=True)

        active_trade = None
        
        for i in range(100, len(df_v18) - 30):
            ts = df_v18.index[i]
            row = df_v18.iloc[i]
            
            if active_trade:
                if active_trade['type'] == "BUY":
                    hit_sl, hit_tp = row['Low'] <= active_trade['sl'], row['High'] >= active_trade['tp']
                else:
                    hit_sl, hit_tp = row['High'] >= active_trade['sl'], row['Low'] <= active_trade['tp']
                
                if hit_sl: self._close(active_trade, active_trade['sl'], ts); active_trade = None
                elif hit_tp: self._close(active_trade, active_trade['tp'], ts); active_trade = None
                continue

            # OMNISCIENT WINDOW CHECK (>3 trades target)
            if not row['is_algo_window']: continue
            
            idm_bull = row['IDM_Sweep_Bull']
            idm_bear = row['IDM_Sweep_Bear']
            bias = row['HTF_Bias']
            
            if (idm_bull and "BULLISH" in bias) or (idm_bear and "BEARISH" in bias):
                swing_low, swing_high = row['Low'], row['High']
                for j in range(1, 10):
                    fwd_row = df_v18.iloc[i + j]
                    swing_low = min(swing_low, fwd_row['Low'])
                    swing_high = max(swing_high, fwd_row['High'])
                    
                    if (idm_bull and fwd_row['CISD_Bull']) or (idm_bear and fwd_row['CISD_Bear']):
                        ote_price = calculate_ote_v15(swing_high, swing_low, "BUY" if idm_bull else "SELL")
                        
                        for k in range(j + 1, j + 20):
                            trig_row = df_v18.iloc[i + k]
                            if (idm_bull and trig_row['Low'] <= ote_price) or (idm_bear and trig_row['High'] >= ote_price):
                                sl = (swing_low - 0.0005) if idm_bull else (swing_high + 0.0005)
                                tp = ote_price + (ote_price - sl) * 2.2 # Back to High Probability 2.2 RR
                                active_trade = {"type": "BUY" if idm_bull else "SELL", "entry": ote_price, "sl": sl, "tp": tp, "time": ts}
                                break
                        if active_trade: break

    def _close(self, trade, price, ts):
        pnl = (price - trade['entry']) if trade['type'] == "BUY" else (trade['entry'] - price)
        self.balance += (pnl * 20000) - 2.0
        self.trades.append(pnl)

    def report(self):
        if not self.trades: return "V18 Omniscient: No trades found."
        df = pd.Series(self.trades)
        wr = (len(df[df > 0]) / len(df)) * 100
        net = self.balance - self.initial_balance
        return f"V18 OMNISCIENT | Trades: {len(df)} | WR: {wr:.1f}% | Net PnL: ${net:.2f} | Avg Trades/Day: {len(df)/30:.1f}"

if __name__ == "__main__":
    bt = OmniscientBacktester()
    bt.run()
    print(bt.report())
