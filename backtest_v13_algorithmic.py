import pandas as pd
import numpy as np
import os
import yfinance as yf
from datetime import datetime, timedelta
import pandas_ta as ta
from ict_utils import (
    download_full_history, get_smc_bias_v11, apply_ict_v13_master, 
    is_in_killzone_v13, is_in_macro_v13
)

class AlgorithmicMasterBacktester:
    def __init__(self):
        self.initial_balance = 1000.0
        self.balance = 1000.0
        self.trades = []

    def run(self, pair1="EUR_USD", pair2="GBP_USD", period="60d"):
        print(f"Running V13 Institutional Audit for {pair1} vs {pair2}...")
        
        # 1. Multi-Asset Data Fetching
        df_main_1h = download_full_history(pair1, interval="1h", period="90d")
        df_main_5m = download_full_history(pair1, interval="5m", period=period)
        df_corr_5m = download_full_history(pair2, interval="5m", period=period)
        
        if df_main_5m.empty or df_corr_5m.empty: 
            print("Missing data.")
            return
        
        # 2. SMT & V13 Enrichment
        df_main_5m, df_corr_5m = df_main_5m.align(df_corr_5m, join='inner', axis=0)
        df_v13 = apply_ict_v13_master(df_main_5m, df_corr_5m)
        
        # Debug: Count SMT signals
        smt_count = len(df_v13[df_v13['SMT_Signal'] != 0])
        print(f"Detected {smt_count} SMT Divergence points.")
        
        # HTF Bias
        df_main_1h['HTF_Bias'] = [get_smc_bias_v11(df_main_1h.iloc[:i+1].tail(20)) for i in range(len(df_main_1h))]
        df_v13 = pd.merge_asof(
            df_v13.sort_index(), 
            df_main_1h[['HTF_Bias']].sort_index(), 
            left_index=True, 
            right_index=True
        )

        # 3. Execution Simulation (Institutional Sequence Engine)
        active_trade = None
        stats = {"found_setups": 0, "killzone": 0, "smt": 0, "fvg": 0}
        
        for i in range(100, len(df_v13) - 10):
            ts = df_v13.index[i]
            row = df_v13.iloc[i]
            
            if active_trade:
                # Institutional Exit Logic
                if active_trade['type'] == "BUY":
                    hit_sl, hit_tp = row['Low'] <= active_trade['sl'], row['High'] >= active_trade['tp']
                else: 
                    hit_sl, hit_tp = row['High'] >= active_trade['sl'], row['Low'] <= active_trade['tp']
                
                if hit_sl: self._close(active_trade, active_trade['sl'], ts, "SL"); active_trade = None
                elif hit_tp: self._close(active_trade, active_trade['tp'], ts, "TP"); active_trade = None
                continue

            # SEQUENCE START: Liquidity Sweep in Silver Bullet Window
            # London (10:00-11:00), NY AM (17:00-18:00), NY PM (21:00-22:00) TSİ
            hour = ts.hour
            is_sb_window = (hour == 10) or (hour == 17) or (hour == 21)
            
            if not is_sb_window: continue
            
            sweep_bull = row['TurtleSoup_Bull']
            sweep_bear = row['TurtleSoup_Bear']
            
            if sweep_bull or sweep_bear:
                stats["killzone"] += 1
                bias = row['HTF_Bias']
                
                # Look ahead for SMT and then FVG (The Sequence)
                for j in range(0, 10): 
                    # ... (rest of search logic same) ...
                    fwd_row = df_v13.iloc[i + j]
                    
                    # 2. SMT Check
                    if fwd_row['SMT_Signal'] != 0:
                        stats["smt"] += 1
                        
                        # 3. FVG Confirmation
                        for k in range(j, j + 10):
                            trig_row = df_v13.iloc[i + k]
                            if sweep_bull and trig_row['FVG_Bull'] and "BULLISH" in bias:
                                active_trade = self._open("BUY", trig_row, df_v13.index[i + k])
                                stats["found_setups"] += 1
                                break
                            elif sweep_bear and trig_row['FVG_Bear'] and "BEARISH" in bias:
                                active_trade = self._open("SELL", trig_row, df_v13.index[i + k])
                                stats["found_setups"] += 1
                                break
                    if active_trade: break
        
        print(f"Sequence Stats: {stats}")

    def _open(self, side, row, ts):
        price = row['Close']
        sl_dist = 0.0012 # Tight institutional Sl
        sl = price - sl_dist if side == "BUY" else price + sl_dist
        tp = price + (sl_dist * 3) if side == "BUY" else price - (sl_dist * 3) # 1:3 RR
        return {"type": side, "entry": price, "sl": sl, "tp": tp, "time": ts, "units": 20000}

    def _close(self, trade, price, ts, status):
        pnl = (price - trade['entry']) if trade['type'] == "BUY" else (trade['entry'] - price)
        net_pnl = (pnl * trade['units']) - 2.0 
        self.balance += net_pnl
        self.trades.append({"pnl": net_pnl, "status": status})

    def report(self):
        if not self.trades: return "V13: No Setups Found."
        df = pd.DataFrame(self.trades)
        wins = len(df[df['pnl'] > 0])
        wr = (wins / len(df)) * 100
        net = self.balance - self.initial_balance
        return f"V13 Institutional | Setups: {len(df)} | WR: {wr:.1f}% | Net PnL: ${net:.2f}"

if __name__ == "__main__":
    bt = AlgorithmicMasterBacktester()
    bt.run("EUR_USD", "GBP_USD")
    print(bt.report())
