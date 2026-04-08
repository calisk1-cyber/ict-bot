import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta, timezone
from oanda_data import download_oanda_candles
from ict_utils import (
    get_smc_bias_v11, apply_ict_v18_omniscient, 
    calculate_ote_v15
)

def calculate_sharpe(returns):
    if len(returns) < 2: return 0
    return (np.mean(returns) / np.std(returns)) * np.sqrt(252)

class OneYearStressTest:
    def __init__(self):
        self.initial_balance = 1000.0
        self.balance = 1000.0
        self.trades_log = []
        self.all_returns = []
        self.symbols = ["USD_JPY", "XAU_USD", "USD_CAD"]
        self.risk_percent = 0.01 # 1% Compounding

    def run(self):
        print("\n" + "="*60)
        print(" SINGULARITY V18 - ONE YEAR INSTITUTIONAL STRESS TEST ")
        print(f" Starting Capital: ${self.initial_balance} | Risk: 1% Compounding")
        print("="*60)
        
        # Date range: Last 12 months
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=365)
        
        from_t = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        to_t = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        for sym in self.symbols:
            print(f"\n--- Processing: {sym} ---")
            # Using pagination for 1 year of data
            df_5m = download_oanda_candles(sym, "M5", from_time=from_t, to_time=to_t)
            df_1h = download_oanda_candles(sym, "H1", from_time=from_t, to_time=to_t)
            
            if df_5m.empty:
                print(f"!! {sym} data could not be fetched.")
                continue
                
            print(f"-> {len(df_5m)} bars downloaded. Processing V18 engine...")
            df_v18 = apply_ict_v18_omniscient(df_5m)
            
            # Simplified HTF Bias for speed over 1 year
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
                        pnl_ratio = (p_price - active_trade['entry']) / (active_trade['sl'] - active_trade['entry'])
                        
                        # Compounding Risk Calculation
                        current_risk_usd = self.balance * self.risk_percent
                        pnl_usd = -(pnl_ratio * current_risk_usd) - 2.5 # $2.5 comm
                        
                        self.balance += pnl_usd
                        self.all_returns.append(pnl_usd)
                        
                        outcome = "TP" if pnl_usd > 0 else "SL"
                        active_trade = None
                    continue

                if not row.get('is_algo_window', False): continue
                
                bias = row.get('HTF_Bias', 'NEUTRAL')
                is_bull = row.get('CISD_Bull') and "BULLISH" in bias
                is_bear = row.get('CISD_Bear') and "BEARISH" in bias
                
                if is_bull or is_bear:
                    ote = calculate_ote_v15(row['High'], row['Low'], "BUY" if is_bull else "SELL")
                    dist = 2.0 if "XAU" in sym else 0.0012
                    sl = (ote - dist) if is_bull else (ote + dist)
                    tp = ote + (ote - sl) * 1.8
                    active_trade = {"type": "BUY" if is_bull else "SELL", "entry": ote, "sl": sl, "tp": tp, "time": row.name}
            
            print(f"-> {sym} processing complete. Total trades so far: {len(self.all_returns)}")
            time.sleep(1)

        self.final_report()

    def final_report(self):
        if not self.all_returns:
            print("No trades found across one year.")
            return

        df = pd.Series(self.all_returns)
        net = self.balance - self.initial_balance
        wr = (len(df[df > 0]) / len(df)) * 100
        sharpe = calculate_sharpe(df)
        pf = abs(df[df > 0].sum() / df[df <= 0].sum()) if len(df[df <= 0]) > 0 else 100
        mdd = (df.cumsum().expanding().max() - df.cumsum()).max()
        
        print("\n" + "="*60)
        print(" FINAL ONE-YEAR STRESS TEST SUMMARY ")
        print("="*60)
        print(f" TOTAL TRADES: {len(df)}")
        print(f" WIN RATE: {wr:.1f}%")
        print(f" PROFIT FACTOR: {pf:.2f}")
        print(f" SHARPE RATIO: {sharpe:.2f}")
        print(f" MAX DRAWDOWN (USD): ${mdd:.2f}")
        print(f" FINAL BALANCE: ${self.balance:.2f}")
        print(f" NET PROFIT: ${net:.2f} ({ (net/self.initial_balance)*100 :.1f}%)")
        print("="*60 + "\n")

if __name__ == "__main__":
    stress_test = OneYearStressTest()
    stress_test.run()
