import pandas as pd
import numpy as np
import os
import sys
from datetime import timedelta, datetime
import pytz

# Path setup
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ict_utils import (
    is_silver_bullet_zone, find_fvg_v3, find_ifvg, find_inducement, 
    is_macro_time, find_turtle_soup, find_smt_proxy, download_full_history
)

class ExpertV3Backtest:
    def __init__(self, csv_path, spread_pips=1.5):
        print(f"Loading data from {csv_path}...")
        self.df = pd.read_csv(csv_path, skiprows=[1, 2])
        self.df.columns = ['Datetime', 'Close', 'High', 'Low', 'Open', 'Volume']
        self.df['Datetime'] = pd.to_datetime(self.df['Datetime'])
        self.df.set_index('Datetime', inplace=True)
        if self.df.index.tz is None:
            self.df.index = self.df.index.tz_localize('UTC')
            
        last_date = self.df.index[-1]
        start_date = last_date - timedelta(days=30)
        self.df = self.df.loc[start_date:]
        
        self.spread = spread_pips * 0.0001
        self.balance = 10000.0
        self.trades = []

    def run(self):
        print("Calculating Expert v3 Indicators (Alpha Injection)...")
        df = self.df.copy()
        
        df = find_turtle_soup(df)
        df = find_fvg_v3(df)
        df = find_ifvg(df)
        df = find_inducement(df)
        
        # SMT Proxy (Simple internal shift check for backtest)
        df['SMT_Bull'] = (df['Low'] < df['Low'].rolling(10).min().shift(1)) & (df['Close'] > df['Low'].rolling(10).min().shift(1))
        
        print("Starting Expert v3 Simulation...")
        active_trade = None
        
        for i in range(50, len(df)):
            ts = df.index[i]
            now = df.iloc[i]
            
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

            # --- ENTRY (V3 Scoring) ---
            if not active_trade:
                score = 0
                is_sb = is_silver_bullet_zone(ts)
                is_macro = is_macro_time(ts)
                
                if is_sb: score += 30
                elif is_macro: score += 20
                
                if now['TurtleSoup_Bull']: score += 25
                if now['IDM_Bull']: score += 15
                if now['FVG_Bull']: score += 20
                if now['IFVG_Bull']: score += 15
                
                # Bearish score
                b_score = 0
                if is_sb: b_score += 30
                elif is_macro: b_score += 20
                if now['TurtleSoup_Bear']: b_score += 25
                if now['IDM_Bear']: b_score += 15
                if now['FVG_Bear']: b_score += 20
                if now['IFVG_Bear']: b_score += 15

                if score >= 75:
                    active_trade = self.open_trade(ts, 'LONG', now['Close'])
                elif b_score >= 75:
                    active_trade = self.open_trade(ts, 'SHORT', now['Close'])

        self.report()

    def open_trade(self, ts, direction, price):
        # 1:3 RR
        sl_dist = 0.0010 # 10 pips
        tp_dist = sl_dist * 3.0
        
        sl = price - sl_dist if direction == 'LONG' else price + sl_dist
        tp = price + tp_dist if direction == 'LONG' else price - tp_dist
        entry = (price + self.spread/2) if direction == 'LONG' else (price - self.spread/2)
        return {'time': ts, 'dir': direction, 'entry': entry, 'sl': sl, 'tp': tp, 'status': 'OPEN'}

    def close_trade(self, trade, price, ts, status):
        trade['status'] = status; trade['exit_price'] = price; trade['exit_time'] = ts
        pips = (price - trade['entry']) if trade['dir'] == 'LONG' else (trade['entry'] - price)
        trade['pnl'] = pips * 10000
        self.balance += (trade['pnl'] * 1.0) # 1 Lot
        self.trades.append(trade)

    def report(self):
        df = pd.DataFrame(self.trades)
        if df.empty: 
            print("No Expert v3 trades found. Filters are extremely high quality.")
            return
        wr = len(df[df['status'] == 'TP']) / len(df) * 100
        print(f"\n--- EXPERT V3 (IFVG + MACRO + IDM) 30-DAY REPORT ---")
        print(f"Total Trades: {len(df)}")
        print(f"Win Rate: {wr:.2f}%")
        print(f"Total PNL: ${self.balance - 10000:.2f}")

if __name__ == "__main__":
    tester = ExpertV3Backtest('eurusd_5m.csv')
    tester.run()
