import pandas as pd
import numpy as np
import os
import yfinance as yf
from datetime import datetime
from ict_utils import (
    download_full_history, get_smc_bias_v11, apply_ict_v16_sovereign, 
    calculate_ote_v15, is_in_killzone_v13
)

class SovereignBacktester:
    def __init__(self):
        self.balance = 1000.0
        self.initial_balance = 1000.0
        self.trades = []

    def run(self, pair1="EUR_USD", pair2="GBP_USD", period="60d"):
        print(f"Executing V16 Sovereign Audit for {pair1} vs {pair2}...")
        
        # 1. Data Fetching
        df_main_1h = download_full_history(pair1, interval="1h", period="90d")
        df_main_5m = download_full_history(pair1, interval="5m", period=period)
        df_corr_5m = download_full_history(pair2, interval="5m", period=period)
        
        if df_main_5m.empty: return
        
        # 2. Enrichment
        df_v16 = apply_ict_v16_sovereign(df_main_5m, df_corr_5m)
        
        # HTF Bias
        df_main_1h['HTF_Bias'] = [get_smc_bias_v11(df_main_1h.iloc[:i+1].tail(20)) for i in range(len(df_main_1h))]
        df_v16 = pd.merge_asof(df_v16.sort_index(), df_main_1h[['HTF_Bias']].sort_index(), left_index=True, right_index=True)

        # 3. Execution (Sovereign Engine)
        active_trade = None
        
        for i in range(100, len(df_v16) - 30):
            ts = df_v16.index[i]
            row = df_v16.iloc[i]
            
            if active_trade:
                if active_trade['type'] == "BUY":
                    hit_sl, hit_tp = row['Low'] <= active_trade['sl'], row['High'] >= active_trade['tp']
                else:
                    hit_sl, hit_tp = row['High'] >= active_trade['sl'], row['Low'] <= active_trade['tp']
                
                if hit_sl: self._close(active_trade, active_trade['sl'], ts, "SL"); active_trade = None
                elif hit_tp: self._close(active_trade, active_trade['tp'], ts, "TP"); active_trade = None
                continue

            # SOVEREIGN SEQUENCE: Weekly Profile + AMD Fractal + Inducement
            # Only trade during London/NY Expansion phases of the AMD fractal
            if not (row['is_london_manip'] or row['is_ny_dist']): continue
            
            idm_bull = row['IDM_Sweep_Bull']
            idm_bear = row['IDM_Sweep_Bear']
            bias = row['HTF_Bias']
            
            # Additional V16 Filter: Tuesday/Wednesday Extreme probability
            is_mon_wed = ts.dayofweek in [0, 1, 2]
            
            if (idm_bull and "BULLISH" in bias and is_mon_wed) or (idm_bear and "BEARISH" in bias and is_mon_wed):
                swing_low, swing_high = row['Low'], row['High']
                for j in range(1, 10):
                    fwd_row = df_v16.iloc[i + j]
                    swing_low = min(swing_low, fwd_row['Low'])
                    swing_high = max(swing_high, fwd_row['High'])
                    
                    if (idm_bull and fwd_row['CISD_Bull']) or (idm_bear and fwd_row['CISD_Bear']):
                        ote_price = calculate_ote_v15(swing_high, swing_low, "BUY" if idm_bull else "SELL")
                        
                        for k in range(j + 1, j + 20):
                            trig_row = df_v16.iloc[i + k]
                            if (idm_bull and trig_row['Low'] <= ote_price) or (idm_bear and trig_row['High'] >= ote_price):
                                sl = (swing_low - 0.0006) if idm_bull else (swing_high + 0.0006)
                                tp = ote_price + (ote_price - sl) * 2.8 # Higher target for Sovereign expansion
                                active_trade = {"type": "BUY" if idm_bull else "SELL", "entry": ote_price, "sl": sl, "tp": tp, "time": ts}
                                break
                        if active_trade: break

    def _close(self, trade, price, ts, status):
        pnl = (price - trade['entry']) if trade['type'] == "BUY" else (trade['entry'] - price)
        self.balance += (pnl * 20000) - 2.0
        self.trades.append(pnl)

    def report(self):
        if not self.trades: return "V16 Sovereign: No trades found."
        df = pd.Series(self.trades)
        wr = (len(df[df > 0]) / len(df)) * 100
        net = self.balance - self.initial_balance
        return f"V15 Sovereign | Trades: {len(df)} | WR: {wr:.1f}% | Net PnL: ${net:.2f}"

if __name__ == "__main__":
    bt = SovereignBacktester()
    bt.run()
    print(bt.report())
