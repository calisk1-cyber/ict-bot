import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timezone
import pandas_ta as ta
from ict_utils import (
    download_full_history, get_smc_bias_v11, apply_ict_v12_depth
)

class AggressiveBacktesterV11:
    def __init__(self, mode="CONSERVATIVE"):
        self.mode = mode # CONSERVATIVE (Score 45) or AGGRESSIVE (Score 20)
        self.balance = 1000.0
        self.initial_balance = 1000.0
        self.trades = []
        self.threshold = 45 if mode == "CONSERVATIVE" else 20

    def run(self, ticker, period="14d"):
        print(f"Running {self.mode} Backtest for {ticker}...")
        
        # 1. Data Fetching
        df_1h = download_full_history(ticker, interval="1h", period="30d")
        df_5m = download_full_history(ticker, interval="5m", period=period)
        
        if df_1h.empty or df_5m.empty:
            print(f"Error: No data for {ticker}")
            return

        # 2. HTF Bias Calculation
        def get_bias(idx):
            sub_df = df_1h.loc[:idx].tail(20)
            return get_smc_bias_v11(sub_df)
            
        # Optimization: pre-calculate bias for 1H and map to 5M
        df_1h['HTF_Bias'] = [get_smc_bias_v11(df_1h.iloc[:i+1].tail(20)) for i in range(len(df_1h))]
        df_5m = pd.merge_asof(
            df_5m.sort_index(), 
            df_1h[['HTF_Bias']].sort_index(), 
            left_index=True, 
            right_index=True
        )

        # 3. Strategy Enrichment (V11)
        try:
            df_5m = apply_ict_v12_depth(df_5m)
        except:
            return
        
        # 4. Simulation
        active_trade = None
        for i in range(20, len(df_5m)):
            ts = df_5m.index[i]
            row = df_5m.iloc[i]
            
            if active_trade:
                # Check Exit
                curr_price = row['Close']
                if active_trade['type'] == "BUY":
                    if row['Low'] <= active_trade['sl']:
                        self._close(active_trade, active_trade['sl'], ts, "SL")
                        active_trade = None
                    elif row['High'] >= active_trade['tp']:
                        self._close(active_trade, active_trade['tp'], ts, "TP")
                        active_trade = None
                else:
                    if row['High'] <= active_trade['sl']: # Wait, Short sl is high
                        # Fix logic for SL/TP in loop
                        pass
                
                # Re-writing clean exit logic
                if active_trade:
                    if active_trade['type'] == "BUY":
                        hit_sl = row['Low'] <= active_trade['sl']
                        hit_tp = row['High'] >= active_trade['tp']
                    else:
                        hit_sl = row['High'] >= active_trade['sl']
                        hit_tp = row['Low'] <= active_trade['tp']
                    
                    if hit_sl:
                        self._close(active_trade, active_trade['sl'], ts, "SL")
                        active_trade = None
                    elif hit_tp:
                        self._close(active_trade, active_trade['tp'], ts, "TP")
                        active_trade = None
                continue

            # Signal Calculation
            score = 0
            if row.get('FVG_Bull'): score += 25
            if row.get('TurtleSoup_Bull'): score += 20
            if row.get('IFVG_Bull'): score += 22
            if row.get('VI_Bull'): score += 15
            if row.get('PO3_Distribution_Bull'): score += 30
            
            if row.get('FVG_Bear'): score -= 25
            if row.get('TurtleSoup_Bear'): score -= 20
            if row.get('IFVG_Bear'): score -= 22
            if row.get('VI_Bear'): score -= 15
            if row.get('PO3_Distribution_Bear'): score -= 30
            
            bias = row.get('HTF_Bias', 'NEUTRAL')
            
            # Entry Logic
            if score >= self.threshold and "BULLISH" in bias and row.get('is_discount', True):
                active_trade = self._open("BUY", row, ts, score)
            elif score <= -self.threshold and "BEARISH" in bias and row.get('is_premium', True):
                active_trade = self._open("SELL", row, ts, score)

    def _open(self, side, row, ts, score):
        price = row['Close']
        atr = 0.0015 # approximation
        sl_dist = atr * 1.5
        sl = price - sl_dist if side == "BUY" else price + sl_dist
        tp = price + (sl_dist * 2) if side == "BUY" else price - (sl_dist * 2)
        
        trade = {
            "type": side, "entry": price, "sl": sl, "tp": tp, 
            "time": ts, "score": score, "units": 10000
        }
        return trade

    def _close(self, trade, price, ts, status):
        pnl = (price - trade['entry']) if trade['type'] == "BUY" else (trade['entry'] - price)
        # Net pnl with spread and comm (approx)
        net_pnl = (pnl * trade['units']) - 2.0 
        self.balance += net_pnl
        trade['exit_price'] = price
        trade['exit_time'] = ts
        trade['status'] = status
        trade['pnl'] = net_pnl
        self.trades.append(trade)

    def report(self):
        if not self.trades:
            return f"Mode {self.mode}: No trades executed."
        
        df = pd.DataFrame(self.trades)
        wins = len(df[df['pnl'] > 0])
        wr = (wins / len(df)) * 100
        net = self.balance - self.initial_balance
        return f"Mode {self.mode} | Trades: {len(df)} | WR: {wr:.1f}% | Net PnL: ${net:.2f}"

if __name__ == "__main__":
    for mode in ["CONSERVATIVE", "AGGRESSIVE"]:
        bt = AggressiveBacktesterV11(mode=mode)
        bt.run("EUR_USD", period="30d")
        print(bt.report())
