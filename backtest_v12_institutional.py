import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timezone
import pandas_ta as ta
from ict_utils import (
    download_full_history, get_smc_bias_v11, apply_ict_v12_depth
)

class InstitutionalBacktesterV12:
    def __init__(self, mode="MODERATE"):
        self.mode = mode 
        self.balance = 1000.0
        self.initial_balance = 1000.0
        self.trades = []
        # V12 Thresholds:
        # Aggressive: 25 (requires FVG + 1 other)
        # Moderate: 45 (requires FVG + 2 others)
        self.threshold = 45 if mode == "CONSERVATIVE" else 25

    def run(self, ticker, period="14d"):
        print(f"Running V12 {self.mode} Backtest for {ticker}...")
        
        df_1h = download_full_history(ticker, interval="1h", period="30d")
        df_5m = download_full_history(ticker, interval="5m", period=period)
        
        if df_1h.empty or df_5m.empty: return

        # SMC Bias
        df_1h['HTF_Bias'] = [get_smc_bias_v11(df_1h.iloc[:i+1].tail(20)) for i in range(len(df_1h))]
        df_5m = pd.merge_asof(df_5m.sort_index(), df_1h[['HTF_Bias']].sort_index(), left_index=True, right_index=True)

        # V12 Enrichment
        df_5m = apply_ict_v12_depth(df_5m)
        
        active_trade = None
        for i in range(20, len(df_5m)):
            ts = df_5m.index[i]
            row = df_5m.iloc[i]
            
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

            # V12 Score (Institutional Weights)
            score = 0
            if row.get('FVG_Bull'): score += 30 # Increased weight for FVG
            if row.get('TurtleSoup_Bull'): score += 20
            if row.get('IFVG_Bull'): score += 25
            if row.get('VI_Bull'): score += 15
            if row.get('PO3_Distribution_Bull'): score += 35
            
            if row.get('FVG_Bear'): score -= 30
            if row.get('TurtleSoup_Bear'): score -= 20
            if row.get('IFVG_Bear'): score -= 25
            if row.get('VI_Bear'): score -= 15
            if row.get('PO3_Distribution_Bear'): score -= 35
            
            bias = row.get('HTF_Bias', 'NEUTRAL')
            
            # Entry: FVG MUST be present for Scoring base (Education Rule)
            # Re-confirming Displacement requirement is already inside find_fvg_v12
            
            if score >= self.threshold and "BULLISH" in bias and row['is_discount']:
                active_trade = self._open("BUY", row, ts, score)
            elif score <= -self.threshold and "BEARISH" in bias and row['is_premium']:
                active_trade = self._open("SELL", row, ts, score)

    def _open(self, side, row, ts, score):
        price = row['Close']
        sl_dist = 0.0016 # 16 pips / points approx
        sl = price - sl_dist if side == "BUY" else price + sl_dist
        tp = price + (sl_dist * 2.5) if side == "BUY" else price - (sl_dist * 2.5) # Higher RR
        
        return {"type": side, "entry": price, "sl": sl, "tp": tp, "time": ts, "score": score, "units": 10000}

    def _close(self, trade, price, ts, status):
        pnl = (price - trade['entry']) if trade['type'] == "BUY" else (trade['entry'] - price)
        net_pnl = (pnl * trade['units']) - 1.5 
        self.balance += net_pnl
        trade['pnl'] = net_pnl
        self.trades.append(trade)

    def report(self):
        if not self.trades: return f"V12 {self.mode}: No trades."
        df = pd.DataFrame(self.trades)
        wins = len(df[df['pnl'] > 0])
        wr = (wins / len(df)) * 100
        net = self.balance - self.initial_balance
        return f"V12 {self.mode} | Trades: {len(df)} | WR: {wr:.1f}% | Net PnL: ${net:.2f}"

if __name__ == "__main__":
    for mode in ["CONSERVATIVE", "MODERATE"]:
        bt = InstitutionalBacktesterV12(mode=mode)
        bt.run("EUR_USD")
        print(bt.report())
        bt = InstitutionalBacktesterV12(mode=mode)
        bt.run("XAU_USD")
        print(bt.report())
