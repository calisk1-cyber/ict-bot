import pandas as pd
import numpy as np
from oanda_data import download_oanda_candles
from ict_utils import (
    get_smc_bias_v11, apply_ict_v18_omniscient, 
    calculate_ote_v15
)

class OandaTitanBacktester:
    def __init__(self):
        self.balance = 1000.0
        self.initial_balance = 1000.0
        self.trades = []

    def run(self, pair1="EUR_USD", pair2="GBP_USD"):
        print(f"Executing V18 OMNISCIENT OANDA Audit for {pair1}...")
        
        # 1. Fetch Oanda Data
        df_main_5m = download_oanda_candles(instrument=pair1, granularity="M5", count=4000)
        df_corr_5m = download_oanda_candles(instrument=pair2, granularity="M5", count=4000)
        df_main_1h = download_oanda_candles(instrument=pair1, granularity="H1", count=1000)
        
        if df_main_5m.empty: 
            print("Failed to fetch Oanda data.")
            return
        
        # 2. Enrichment
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

            if not row['is_algo_window']: continue
            
            idm_bull = row['IDM_Sweep_Bull']
            idm_bear = row['IDM_Sweep_Bear']
            bias = row['HTF_Bias']
            
            # AGGRESSIVE: In Silver Bullet windows, we only need CISD + OTE
            setup_bull = (idm_bull or row['is_algo_window']) and "BULLISH" in bias
            setup_bear = (idm_bear or row['is_algo_window']) and "BEARISH" in bias
            
            if setup_bull or setup_bear:
                swing_low, swing_high = row['Low'], row['High']
                for j in range(1, 10):
                    fwd_row = df_v18.iloc[i + j]
                    swing_low = min(swing_low, fwd_row['Low'])
                    swing_high = max(swing_high, fwd_row['High'])
                    
                    if (setup_bull and fwd_row['CISD_Bull']) or (setup_bear and fwd_row['CISD_Bear']):
                        ote_price = calculate_ote_v15(swing_high, swing_low, "BUY" if setup_bull else "SELL")
                        
                        for k in range(j + 1, j + 20):
                            trig_row = df_v18.iloc[i + k]
                            if (setup_bull and trig_row['Low'] <= ote_price) or (setup_bear and trig_row['High'] >= ote_price):
                                sl = (swing_low - 0.0004) if setup_bull else (swing_high + 0.0004)
                                tp = ote_price + (ote_price - sl) * 1.8 # Aggressive 1.8 RR for Oanda
                                active_trade = {"type": "BUY" if setup_bull else "SELL", "entry": ote_price, "sl": sl, "tp": tp, "time": ts}
                                break
                        if active_trade: break

    def _close(self, trade, price, ts):
        pnl = (price - trade['entry']) if trade['type'] == "BUY" else (trade['entry'] - price)
        # Oanda 20k units equivalent for backtest
        self.balance += (pnl * 20000) - 2.0 # $2 Commission per trade
        self.trades.append(pnl)

    def report(self):
        if not self.trades: return "Oanda V18: No trades found."
        df = pd.Series(self.trades)
        wr = (len(df[df > 0]) / len(df)) * 100
        net = self.balance - self.initial_balance
        return f"Oanda V18 OMNISCIENT | Trades: {len(df)} | WR: {wr:.1f}% | Net PnL: ${net:.2f}"

if __name__ == "__main__":
    bt = OandaTitanBacktester()
    bt.run()
    print(bt.report())
