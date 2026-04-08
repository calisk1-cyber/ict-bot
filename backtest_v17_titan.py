import pandas as pd
import numpy as np
import os
import yfinance as yf
from datetime import datetime
from ict_utils import (
    download_full_history, get_smc_bias_v11, apply_ict_v16_sovereign, 
    calculate_ote_v15, is_in_killzone_v13
)

class TitanBacktester:
    def __init__(self):
        self.balance = 1000.0
        self.initial_balance = 1000.0
        self.trades = []
        self.risk_pct = 0.025 # Aggressive 2.5% Risk

    def run(self, pair1="EUR_USD", pair2="GBP_USD", period="60d"):
        print(f"Executing V17 TITAN Audit (2.5% Compounding) for {pair1}...")
        
        df_main_1h = download_full_history(pair1, interval="1h", period="90d")
        df_main_5m = download_full_history(pair1, interval="5m", period=period)
        df_corr_5m = download_full_history(pair2, interval="5m", period=period)
        
        if df_main_5m.empty: return
        
        df_v17 = apply_ict_v16_sovereign(df_main_5m, df_corr_5m)
        
        df_main_1h['HTF_Bias'] = [get_smc_bias_v11(df_main_1h.iloc[:i+1].tail(20)) for i in range(len(df_main_1h))]
        df_v17 = pd.merge_asof(df_v17.sort_index(), df_main_1h[['HTF_Bias']].sort_index(), left_index=True, right_index=True)

        active_trade = None
        
        for i in range(100, len(df_v17) - 30):
            ts = df_v17.index[i]
            row = df_v17.iloc[i]
            
            if active_trade:
                if active_trade['type'] == "BUY":
                    hit_sl, hit_tp = row['Low'] <= active_trade['sl'], row['High'] >= active_trade['tp']
                else:
                    hit_sl, hit_tp = row['High'] >= active_trade['sl'], row['Low'] <= active_trade['tp']
                
                if hit_sl: self._close(active_trade, active_trade['sl'], ts); active_trade = None
                elif hit_tp: self._close(active_trade, active_trade['tp'], ts); active_trade = None
                continue

            if not (row['is_london_manip'] or row['is_ny_dist']): continue
            
            idm_bull = row['IDM_Sweep_Bull']
            idm_bear = row['IDM_Sweep_Bear']
            bias = row['HTF_Bias']
            is_mon_wed = ts.dayofweek in [0, 1, 2]
            
            if (idm_bull and "BULLISH" in bias and is_mon_wed) or (idm_bear and "BEARISH" in bias and is_mon_wed):
                swing_low, swing_high = row['Low'], row['High']
                for j in range(1, 10):
                    fwd_row = df_v17.iloc[i + j]
                    swing_low = min(swing_low, fwd_row['Low'])
                    swing_high = max(swing_high, fwd_row['High'])
                    
                    if (idm_bull and fwd_row['CISD_Bull']) or (idm_bear and fwd_row['CISD_Bear']):
                        ote_price = calculate_ote_v15(swing_high, swing_low, "BUY" if idm_bull else "SELL")
                        
                        for k in range(j + 1, j + 20):
                            trig_row = df_v17.iloc[i + k]
                            if (idm_bull and trig_row['Low'] <= ote_price) or (idm_bear and trig_row['High'] >= ote_price):
                                sl = (swing_low - 0.0006) if idm_bull else (swing_high + 0.0006)
                                tp = ote_price + (ote_price - sl) * 2.2 # BALANCED TITAN 1:2.2
                                
                                # Dynamic Position Size
                                sl_pips = abs(ote_price - sl) * 10000
                                if sl_pips < 2: sl_pips = 2
                                risk_amt = self.balance * 0.02 # 2% Compounding
                                units = (risk_amt / sl_pips) * 1000
                                
                                active_trade = {"type": "BUY" if idm_bull else "SELL", "entry": ote_price, "sl": sl, "tp": tp, "units": units, "time": ts}
                                break
                        if active_trade: break

    def _close(self, trade, price, ts):
        pips = (price - trade['entry']) if trade['type'] == "BUY" else (trade['entry'] - price)
        pnl = (pips * trade['units']) - 2.0 # Commission
        self.balance += pnl
        self.trades.append(pnl)

    def report(self):
        if not self.trades: return "V17 Titan: No trades found."
        df = pd.Series(self.trades)
        wr = (len(df[df > 0]) / len(df)) * 100
        net = self.balance - self.initial_balance
        return f"V17 TITAN | Trades: {len(df)} | WR: {wr:.1f}% | Net PnL: ${net:.2f} | ROI: {(net/self.initial_balance)*100:.1f}%"

if __name__ == "__main__":
    bt = TitanBacktester()
    bt.run()
    print(bt.report())
