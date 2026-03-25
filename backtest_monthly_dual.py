import pandas as pd
import numpy as np
import os
import sys
import pytz
from datetime import timedelta

# Path setup
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ict_utils import find_turtle_soup, find_fvg_v3, is_silver_bullet_zone, find_order_blocks

class DualEngineMonthlyBacktest:
    def __init__(self, csv_5m, spread_pips=1.5):
        print("Loading 5m data...")
        self.df_5m = pd.read_csv(csv_5m, skiprows=[1, 2])
        self.df_5m.columns = ['Datetime', 'Close', 'High', 'Low', 'Open', 'Volume']
        self.df_5m['Datetime'] = pd.to_datetime(self.df_5m['Datetime'])
        self.df_5m.set_index('Datetime', inplace=True)
        if self.df_5m.index.tz is None:
            self.df_5m.index = self.df_5m.index.tz_localize('UTC')
            
        last_date = self.df_5m.index[-1]
        start_date = last_date - timedelta(days=30)
        self.df_5m = self.df_5m.loc[start_date:]
        
        self.spread = spread_pips * 0.0001
        self.trades = []
        self.balance = 10000.0

    def run(self):
        print("Generating 1H and 5m DataFrames...")
        df_1h = self.df_5m.resample('1h').last().ffill()
        df_1h['EMA_200'] = df_1h['Close'].ewm(span=200, adjust=False).mean()
        df_1h = find_turtle_soup(df_1h, lookback=10)
        df_1h = find_fvg_v3(df_1h)
        
        df_5m = self.df_5m.copy()
        df_5m = find_turtle_soup(df_5m, lookback=20)
        df_5m = find_fvg_v3(df_5m)
        df_5m['Is_SB'] = [is_silver_bullet_zone(ts) for ts in df_5m.index]
        
        active_trade = None
        
        for i in range(100, len(self.df_5m)):
            ts = self.df_5m.index[i]
            now = self.df_5m.iloc[i]
            
            # --- EXIT ---
            if active_trade:
                if active_trade['dir'] == 'LONG':
                    if now['Low'] <= active_trade['sl']:
                        self.close_trade(active_trade, active_trade['sl'], ts, 'SL'); active_trade = None
                    elif now['High'] >= active_trade['tp']:
                        self.close_trade(active_trade, active_trade['tp'], ts, 'TP'); active_trade = None
                else: # SHORT
                    if now['High'] >= active_trade['sl']:
                        self.close_trade(active_trade, active_trade['sl'], ts, 'SL'); active_trade = None
                    elif now['Low'] <= active_trade['tp']:
                        self.close_trade(active_trade, active_trade['tp'], ts, 'TP'); active_trade = None

            # --- ENTRY ---
            if not active_trade:
                # Context
                bias_1h = "BULL" if df_1h.loc[:ts].iloc[-1]['Close'] > df_1h.loc[:ts].iloc[-1]['EMA_200'] else "BEAR"
                
                # Logic A: INTRADAY (1H)
                if ts.minute == 0:
                    h1 = df_1h.loc[ts]
                    if bias_1h == "BULL" and h1['FVG_Bull']:
                        active_trade = self.open_trade(ts, 'LONG', now['Close'], 'INTRADAY', 1.5, 4.0)
                    elif bias_1h == "BEAR" and h1['FVG_Bear']:
                        active_trade = self.open_trade(ts, 'SHORT', now['Close'], 'INTRADAY', 1.5, 4.0)
                
                # Logic B: SCALPING (5m SB)
                if not active_trade and df_5m.loc[ts]['Is_SB']:
                    sc = df_5m.loc[ts]
                    # Sequence Check: Sweep (last 15) then FVG
                    recent = df_5m.iloc[i-15:i+1]
                    if bias_1h == "BULL" and recent['TurtleSoup_Bull'].any() and sc['FVG_Bull']:
                        active_trade = self.open_trade(ts, 'LONG', now['Close'], 'SCALP', 1.0, 3.0)
                    elif bias_1h == "BEAR" and recent['TurtleSoup_Bear'].any() and sc['FVG_Bear']:
                        active_trade = self.open_trade(ts, 'SHORT', now['Close'], 'SCALP', 1.0, 3.0)

        self.report()

    def open_trade(self, ts, direction, price, mode, sl_mult, tp_mult):
        atr = self.df_5m['Close'].iloc[-14:].diff().abs().mean() or 0.0005
        sl = price - (atr * sl_mult) if direction == 'LONG' else price + (atr * sl_mult)
        tp = price + (atr * tp_mult) if direction == 'LONG' else price - (atr * tp_mult)
        entry = (price + self.spread/2) if direction == 'LONG' else (price - self.spread/2)
        return {'time': ts, 'dir': direction, 'entry': entry, 'sl': sl, 'tp': tp, 'status': 'OPEN', 'mode': mode}

    def close_trade(self, trade, price, ts, status):
        trade['status'] = status; trade['exit_price'] = price; trade['exit_time'] = ts
        pips = (price - trade['entry']) if trade['dir'] == 'LONG' else (trade['entry'] - price)
        trade['pnl'] = pips * 10000
        lot = 1.0 if trade['mode'] == 'INTRADAY' else 0.5
        self.balance += (trade['pnl'] * lot)
        self.trades.append(trade)

    def report(self):
        df = pd.DataFrame(self.trades)
        if df.empty: print("No trades triggered."); return
        wr = len(df[df['status'] == 'TP']) / len(df) * 100
        print(f"\n--- REFINED 30-DAY REPORT ---")
        print(f"Trades: {len(df)} (Intraday: {sum(df['mode']=='INTRADAY')}, Scalp: {sum(df['mode']=='SCALP')})")
        print(f"Win Rate: {wr:.2f}%")
        print(f"Total PNL: ${self.balance - 10000:.2f}")
        df.to_csv('monthly_dual_results.csv')

if __name__ == "__main__":
    tester = DualEngineMonthlyBacktest('eurusd_5m.csv')
    tester.run()
