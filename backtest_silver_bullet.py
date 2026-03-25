import pandas as pd
import numpy as np
import os
import sys
import pytz

# Path setup to import utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ict_utils import find_turtle_soup, find_order_blocks, is_silver_bullet_zone, find_fvg_v3

class SilverBulletBacktest:
    def __init__(self, csv_path, spread_pips=1.5, slippage_pips=0.2):
        print("Loading and preparing data...")
        self.df = pd.read_csv(csv_path, skiprows=[1, 2])
        self.df.columns = ['Datetime', 'Close', 'High', 'Low', 'Open', 'Volume']
        self.df['Datetime'] = pd.to_datetime(self.df['Datetime'])
        self.df.set_index('Datetime', inplace=True)
        # Ensure UTC
        if self.df.index.tz is None:
            self.df.index = self.df.index.tz_localize('UTC')
        
        self.spread = spread_pips * 0.0001
        self.slippage = slippage_pips * 0.0001
        self.trades = []
        self.balance = 10000.0
        
    def run(self):
        print("Pre-calculating ICT Indicators (Silver Bullet v2)...")
        # 1. Higher Timeframe Bias (1h)
        df_1h = self.df.resample('1h').last().ffill()
        df_1h['EMA_200'] = df_1h['Close'].ewm(span=200, adjust=False).mean()
        
        # Mapping Bias to 5m
        self.df['Bias'] = np.where(self.df.index.map(lambda x: df_1h.loc[:x].iloc[-1]['Close'] > df_1h.loc[:x].iloc[-1]['EMA_200'] if not df_1h.loc[:x].empty else False), "BULL", "BEAR")
        
        # 2. Indicators
        self.df = find_turtle_soup(self.df, lookback=20)
        self.df = find_fvg_v3(self.df)
        
        # 3. Time Filter
        self.df['Is_Silver_Bullet'] = [is_silver_bullet_zone(ts) for ts in self.df.index]
        
        print("Starting Trade Simulation...")
        active_trade = None
        
        for i in range(50, len(self.df)):
            now = self.df.iloc[i]
            ts = self.df.index[i]
            
            # --- EXIT LOGIC ---
            if active_trade:
                if active_trade['dir'] == 'LONG':
                    if now['Low'] <= active_trade['sl']:
                        active_trade['status'] = 'SL'; active_trade['exit_price'] = active_trade['sl']; active_trade['exit_time'] = ts
                        self.close_trade(active_trade); active_trade = None
                    elif now['High'] >= active_trade['tp']:
                        active_trade['status'] = 'TP'; active_trade['exit_price'] = active_trade['tp']; active_trade['exit_time'] = ts
                        self.close_trade(active_trade); active_trade = None
                else: # SHORT
                    if now['High'] >= active_trade['sl']:
                        active_trade['status'] = 'SL'; active_trade['exit_price'] = active_trade['sl']; active_trade['exit_time'] = ts
                        self.close_trade(active_trade); active_trade = None
                    elif now['Low'] <= active_trade['tp']:
                        active_trade['status'] = 'TP'; active_trade['exit_price'] = active_trade['tp']; active_trade['exit_time'] = ts
                        self.close_trade(active_trade); active_trade = None
            
            # --- ENTRY LOGIC (Silver Bullet Only) ---
            if not active_trade and now['Is_Silver_Bullet']:
                signal_dir = "HOLD"
                
                # Check for Sweep in last 10 candles (TurtleSoup)
                recent_window = self.df.iloc[i-10:i+1]
                has_bull_sweep = recent_window['TurtleSoup_Bull'].any()
                has_bear_sweep = recent_window['TurtleSoup_Bear'].any()
                
                # Setup: Bias + Sweep + Displacement FVG
                if now['Bias'] == "BULL" and has_bull_sweep and now['FVG_Bull']:
                    signal_dir = "LONG"
                elif now['Bias'] == "BEAR" and has_bear_sweep and now['FVG_Bear']:
                    signal_dir = "SHORT"
                
                if signal_dir != "HOLD":
                    entry_price = now['Close']
                    if signal_dir == "LONG": entry_price += (self.spread / 2) + self.slippage
                    else: entry_price -= (self.spread / 2) + self.slippage
                    
                    # 1:2 RR as requested
                    atr = self.df['Close'].iloc[i-14:i].diff().abs().mean() or 0.0005
                    sl_dist = atr * 1.0 # Tighter for scalp
                    tp_dist = sl_dist * 2.0
                    
                    sl = entry_price - sl_dist if signal_dir == "LONG" else entry_price + sl_dist
                    tp = entry_price + tp_dist if signal_dir == "LONG" else entry_price - tp_dist
                    
                    active_trade = {'time': ts, 'dir': signal_dir, 'entry': entry_price, 'sl': sl, 'tp': tp, 'status': 'OPEN'}
                    self.trades.append(active_trade)

        self.report()

    def close_trade(self, trade):
        pips = (trade['exit_price'] - trade['entry']) if trade['dir'] == 'LONG' else (trade['entry'] - trade['exit_price'])
        trade['pnl'] = pips * 10000
        self.balance += trade['pnl']

    def report(self):
        df_trades = pd.DataFrame(self.trades)
        if df_trades.empty:
            print("No trades executed within Silver Bullet windows.")
            return
        closed = df_trades[df_trades['status'] != 'OPEN']
        if closed.empty:
            print("No trades closed.")
            return
        win_rate = len(closed[closed['status']=='TP']) / len(closed) * 100
        print(f"\n--- SILVER BULLET v2 RESULTS ---")
        print(f"Total Trades: {len(closed)}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Profit (Pips): {closed['pnl'].sum():.2f}")
        print(f"Final Balance: ${self.balance:.2f}")

if __name__ == "__main__":
    tester = SilverBulletBacktest('eurusd_5m.csv')
    tester.run()
