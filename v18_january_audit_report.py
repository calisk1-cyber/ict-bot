import pandas as pd
import numpy as np
import os
from oanda_data import download_oanda_candles
from ict_utils import (
    get_smc_bias_v11, apply_ict_v18_omniscient, 
    calculate_ote_v15
)

def calculate_sharpe(returns):
    if len(returns) < 2: return 0
    return (np.mean(returns) / np.std(returns)) * np.sqrt(252) # Simplified annualized

class JanuaryAuditReport:
    def __init__(self):
        self.initial_balance = 1000.0
        self.balance = 1000.0
        self.trades = []
        self.symbols = ["EUR_USD", "XAU_USD"]

    def run(self):
        print("\n" + "="*50)
        print(" SINGULARITY V18 - JANUARY 2024 INSTITUTIONAL AUDIT ")
        print("="*50)
        
        from_t = "2024-01-01T00:00:00Z"
        to_t = "2024-02-01T00:00:00Z"
        
        for sym in self.symbols:
            print(f"Analyzing {sym} for January...")
            df_5m = download_oanda_candles(sym, "M5", from_time=from_t, to_time=to_t)
            df_1h = download_oanda_candles(sym, "H1", from_time=from_t, to_time=to_t)
            
            if df_5m.empty: continue
            
            df_v18 = apply_ict_v18_omniscient(df_5m)
            df_1h['HTF_Bias'] = [get_smc_bias_v11(df_1h.iloc[:i+1].tail(20)) for i in range(len(df_1h))]
            df_v18 = pd.merge_asof(df_v18.sort_index(), df_1h[['HTF_Bias']].sort_index(), left_index=True, right_index=True)

            active_trade = None
            for i in range(100, len(df_v18) - 30):
                row = df_v18.iloc[i]
                if active_trade:
                    hit_sl, hit_tp = False, False
                    if active_trade['type'] == "BUY":
                        hit_sl, hit_tp = row['Low'] <= active_trade['sl'], row['High'] >= active_trade['tp']
                    else:
                        hit_sl, hit_tp = row['High'] >= active_trade['sl'], row['Low'] <= active_trade['tp']
                    
                    if hit_sl or hit_tp:
                        p_price = active_trade['sl'] if hit_sl else active_trade['tp']
                        pnl_pts = (p_price - active_trade['entry']) if active_trade['type'] == "BUY" else (active_trade['entry'] - p_price)
                        mult = 100 if "XAU" in sym else 20000
                        self.balance += (pnl_pts * mult) - 2.0
                        self.trades.append(pnl_pts * mult)
                        active_trade = None
                    continue

                if not row['is_algo_window']: continue
                bias = row['HTF_Bias']
                is_bull = row['CISD_Bull'] and "BULLISH" in bias
                is_bear = row['CISD_Bear'] and "BEARISH" in bias
                
                if is_bull or is_bear:
                    ote = calculate_ote_v15(row['High'], row['Low'], "BUY" if is_bull else "SELL")
                    dist = 2.0 if "XAU" in sym else 0.0012
                    sl = (ote - dist) if is_bull else (ote + dist)
                    tp = ote + (ote - sl) * 1.8
                    active_trade = {"type": "BUY" if is_bull else "SELL", "entry": ote, "sl": sl, "tp": tp}

        self.generate_report()

    def generate_report(self):
        if not self.trades:
            print("No trades found for January Audit.")
            return

        df_trades = pd.Series(self.trades)
        wins = df_trades[df_trades > 0]
        losses = df_trades[df_trades <= 0]
        
        wr = (len(wins) / len(df_trades)) * 100
        net = self.balance - self.initial_balance
        pf = abs(wins.sum() / losses.sum()) if not losses.empty else 0
        sharpe = calculate_sharpe(df_trades)
        mdd = (df_trades.cumsum().expanding().max() - df_trades.cumsum()).max()
        
        print("\n" + "-"*50)
        print(f" STATUS: AUDIT COMPLETE")
        print(f" TOTAL TRADES: {len(df_trades)}")
        print(f" WIN RATE: {wr:.1f}%")
        print(f" PROFIT FACTOR: {pf:.2f}")
        print(f" SHARPE RATIO: {sharpe:.2f}")
        print(f" MAX DRAWDOWN: ${mdd:.2f}")
        print(f" NET PROFIT: ${net:.2f}")
        print("-"*50)
        
        status = "INSTITUTIONAL GRADE" if sharpe > 1.5 and pf > 1.8 else "STABLE"
        print(f" OVERALL RATING: {status}")
        print("="*50 + "\n")

if __name__ == "__main__":
    report = JanuaryAuditReport()
    report.run()
