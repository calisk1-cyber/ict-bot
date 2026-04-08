import pandas as pd
import numpy as np
import time
from oanda_data import download_oanda_candles
from ict_utils import (
    get_smc_bias_v11, apply_ict_v18_omniscient, 
    calculate_ote_v15
)

class OmniscientPortfolioBacktester:
    def __init__(self):
        self.initial_balance = 1000.0
        self.portfolio_results = []
        self.symbols = ["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD", "AUD_USD"]

    def run_single(self, symbol):
        print(f"--- Denetleniyor: {symbol} ---")
        balance = 1000.0
        trades = []
        
        # 1. Fetch Data
        gran = "M5"
        df_5m = download_oanda_candles(instrument=symbol, granularity=gran, count=3000)
        df_1h = download_oanda_candles(instrument=symbol, granularity="H1", count=1000)
        
        if df_5m.empty: return None
        
        # 2. Enrichment
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
                    
                    # Scaling for Gold vs Forex
                    multiplier = 100 if "XAU" in symbol else 20000
                    balance += (pnl_pts * multiplier) - 2.0
                    trades.append(pnl_pts)
                    active_trade = None
                continue

            if not row['is_algo_window']: continue
            
            bias = row['HTF_Bias']
            setup_bull = (row['IDM_Sweep_Bull'] or True) and row['CISD_Bull'] and "BULLISH" in bias
            setup_bear = (row['IDM_Sweep_Bear'] or True) and row['CISD_Bear'] and "BEARISH" in bias
            
            if setup_bull or setup_bear:
                sl_dist = 2.0 if "XAU" in symbol else 0.0012
                ote_price = calculate_ote_v15(row['High'], row['Low'], "BUY" if setup_bull else "SELL")
                sl = (ote_price - sl_dist) if setup_bull else (ote_price + sl_dist)
                tp = ote_price + (ote_price - sl) * 1.8
                active_trade = {"type": "BUY" if setup_bull else "SELL", "entry": ote_price, "sl": sl, "tp": tp}
        
        if not trades: return None
        wr = (len([t for t in trades if t > 0]) / len(trades)) * 100
        net = balance - 1000.0
        return {"Symbol": symbol, "Trades": len(trades), "WR": f"{wr:.1f}%", "PnL": f"${net:.2f}"}

    def run_all(self):
        print("V18 FULL PORTFOLIO AUDIT STARTING...")
        for sym in self.symbols:
            res = self.run_single(sym)
            if res: self.portfolio_results.append(res)
            time.sleep(1)
            
        print("\n" + "="*40)
        print("FINAL PORTFOLIO SUMMARY (V18 OMNISCIENT)")
        print("="*40)
        pdf = pd.DataFrame(self.portfolio_results)
        print(pdf.to_string(index=False))
        print("="*40)

if __name__ == "__main__":
    bt = OmniscientPortfolioBacktester()
    bt.run_all()
