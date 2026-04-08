import pandas as pd
import numpy as np
from oanda_data import download_oanda_candles
from ict_utils import (
    get_smc_bias_v11, apply_ict_v18_omniscient, 
    calculate_ote_v15
)

class GoldOmniscientBacktester:
    def __init__(self):
        self.balance = 1000.0
        self.initial_balance = 1000.0
        self.trades = []

    def run(self, symbol="XAU_USD"):
        print(f"Executing V18 OMNISCIENT GOLD Audit for {symbol}...")
        
        # 1. Fetch Oanda Gold Data (M5)
        df_main_5m = download_oanda_candles(instrument=symbol, granularity="M5", count=4000)
        df_main_1h = download_oanda_candles(instrument=symbol, granularity="H1", count=1000)
        
        if df_main_5m.empty: return
        
        # 2. Enrichment
        df_v18 = apply_ict_v18_omniscient(df_main_5m)
        
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
            
            bias = row['HTF_Bias']
            is_bull = row['CISD_Bull'] and "BULLISH" in bias
            is_bear = row['CISD_Bear'] and "BEARISH" in bias
            
            if is_bull or is_bear:
                swing_low, swing_high = row['Low'], row['High']
                # Gold needs wider SL but we use OTE for precision
                ote_price = calculate_ote_v15(swing_high, swing_low, "BUY" if is_bull else "SELL")
                
                sl_pips = 2.0 # 20 pips for Gold
                sl = (ote_price - sl_pips) if is_bull else (ote_price + sl_pips)
                tp = ote_price + (ote_price - sl) * 1.8 
                
                active_trade = {"type": "BUY" if is_bull else "SELL", "entry": ote_price, "sl": sl, "tp": tp, "time": ts}

    def _close(self, trade, price, ts):
        pnl_pts = (price - trade['entry']) if trade['type'] == "BUY" else (trade['entry'] - price)
        # Gold 0.1 lot scaling
        self.balance += (pnl_pts * 100) - 2.5 # Slightly higher commission for Gold
        self.trades.append(pnl_pts)

    def report(self):
        if not self.trades: return "Gold V18: No trades found."
        df = pd.Series(self.trades)
        wr = (len(df[df > 0]) / len(df)) * 100
        net = self.balance - self.initial_balance
        return f"GOLD V18 OMNISCIENT | Trades: {len(df)} | WR: {wr:.1f}% | Net PnL: ${net:.2f}"

if __name__ == "__main__":
    bt = GoldOmniscientBacktester()
    bt.run()
    print(bt.report())
