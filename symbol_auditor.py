import pandas as pd
import numpy as np
from oanda_data import download_oanda_candles
from ict_utils import (
    get_smc_bias_v11, apply_ict_v18_omniscient, 
    calculate_ote_v15
)

class SymbolAuditor:
    def __init__(self):
        self.symbols = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "NZD_USD", "XAU_USD"]
        from_t = "2024-02-01T00:00:00Z"
        to_t = "2024-03-01T00:00:00Z"
        self.results = []

        for sym in self.symbols:
            print(f"Auditing {sym}...")
            df_5m = download_oanda_candles(sym, "M5", from_time=from_t, to_time=to_t)
            df_1h = download_oanda_candles(sym, "H1", from_time=from_t, to_time=to_t)
            
            if df_5m.empty: continue
            
            df_v18 = apply_ict_v18_omniscient(df_5m)
            df_1h['HTF_Bias'] = [get_smc_bias_v11(df_1h.iloc[:i+1].tail(20)) for i in range(len(df_1h))]
            df_v18 = pd.merge_asof(df_v18.sort_index(), df_1h[['HTF_Bias']].sort_index(), left_index=True, right_index=True)

            trades = []
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
                        # Simple PnL multiplier for comparison
                        pnl = 1.8 if hit_tp else -1.0
                        trades.append(pnl)
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

            if trades:
                wr = len([t for t in trades if t > 0]) / len(trades)
                pnl_sum = sum(trades)
                self.results.append({"Symbol": sym, "Trades": len(trades), "WR": wr*100, "PnL_Score": pnl_sum})

    def report(self):
        df = pd.DataFrame(self.results).sort_values("PnL_Score", ascending=False)
        print("\n" + "="*50)
        print(" SYMBOL PERFORMANCE RANKING (FEBRUARY 2024) ")
        print("="*50)
        print(df.to_string(index=False))
        print("="*50)

if __name__ == "__main__":
    SymbolAuditor().report()
