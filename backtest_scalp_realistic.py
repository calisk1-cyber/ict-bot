import pandas as pd
import numpy as np
import os
import sys

# Path setup to import utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ict_utils import find_turtle_soup, find_order_blocks, detect_amd_phases

class ScalpBacktest:
    def __init__(self, csv_path, spread_pips=1.5, slippage_pips=0.2):
        print("Loading and preparing data...")
        self.df = pd.read_csv(csv_path, skiprows=[1, 2])
        self.df.columns = ['Datetime', 'Close', 'High', 'Low', 'Open', 'Volume']
        self.df['Datetime'] = pd.to_datetime(self.df['Datetime'])
        self.df.set_index('Datetime', inplace=True)
        
        self.spread = spread_pips * 0.0001
        self.slippage = slippage_pips * 0.0001
        self.trades = []
        self.balance = 10000.0
        
    def run(self):
        print("Pre-calculating ICT Indicators (Vectorized)...")
        # 1. Higher Timeframe Bias (1h)
        df_1h = self.df.resample('1h').last().ffill()
        df_1h['EMA_200'] = df_1h['Close'].ewm(span=200, adjust=False).mean()
        
        # Map bias back to 5m
        self.df['Bias'] = np.where(self.df.index.map(lambda x: df_1h.loc[:x].iloc[-1]['Close'] > df_1h.loc[:x].iloc[-1]['EMA_200'] if not df_1h.loc[:x].empty else False), "BULL", "BEAR")
        
        # 2. Scalp Signals (5m)
        self.df = find_turtle_soup(self.df, lookback=20)
        self.df = find_order_blocks(self.df)
        self.df = detect_amd_phases(self.df)
        
        print("Starting Trade Simulation...")
        active_trade = None
        
        for i in range(50, len(self.df)):
            now = self.df.iloc[i]
            ts = self.df.index[i]
            
            # --- EXIT LOGIC ---
            if active_trade:
                if active_trade['dir'] == 'LONG':
                    if now['Low'] <= active_trade['sl']:
                        active_trade['status'] = 'SL'
                        active_trade['exit_price'] = active_trade['sl']
                        active_trade['exit_time'] = ts
                        self.close_trade(active_trade)
                        active_trade = None
                    elif now['High'] >= active_trade['tp']:
                        active_trade['status'] = 'TP'
                        active_trade['exit_price'] = active_trade['tp']
                        active_trade['exit_time'] = ts
                        self.close_trade(active_trade)
                        active_trade = None
                else: # SHORT
                    if now['High'] >= active_trade['sl']:
                        active_trade['status'] = 'SL'
                        active_trade['exit_price'] = active_trade['sl']
                        active_trade['exit_time'] = ts
                        self.close_trade(active_trade)
                        active_trade = None
                    elif now['Low'] <= active_trade['tp']:
                        active_trade['status'] = 'TP'
                        active_trade['exit_price'] = active_trade['tp']
                        active_trade['exit_time'] = ts
                        self.close_trade(active_trade)
                        active_trade = None
            
            # --- ENTRY LOGIC ---
            if not active_trade:
                # Score Calculation
                score = 0
                signal_dir = "HOLD"
                
                # Turtle Soup (Highest Weight for Scalp)
                if now.get('TurtleSoup_Bull') and now['Bias'] == "BULL": score += 60
                if now.get('TurtleSoup_Bear') and now['Bias'] == "BEAR": score += 60
                
                # Order Block
                if not pd.isna(now.get('Bullish_OB_Price')) and now['Bias'] == "BULL" and now['Low'] <= now['Bullish_OB_Price']: score += 40
                if not pd.isna(now.get('Bearish_OB_Price')) and now['Bias'] == "BEAR" and now['High'] >= now['Bearish_OB_Price']: score += 40
                
                # AMD
                if now.get('AMD_Bull') and now['Bias'] == "BULL": score += 30
                if now.get('AMD_Bear') and now['Bias'] == "BEAR": score += 30
                
                if score >= 70:
                    signal_dir = "LONG" if now['Bias'] == "BULL" else "SHORT"
                    
                if signal_dir != "HOLD":
                    entry_price = now['Close']
                    if signal_dir == "LONG":
                        entry_price += (self.spread / 2) + self.slippage
                    else:
                        entry_price -= (self.spread / 2) + self.slippage
                    
                    # ATR for SL/TP (Approximate ATR 14)
                    atr = self.df['Close'].iloc[i-14:i].diff().abs().mean() or 0.0005
                    sl = entry_price - (atr * 1.5) if signal_dir == "LONG" else entry_price + (atr * 1.5)
                    tp = entry_price + (atr * 3.0) if signal_dir == "LONG" else entry_price - (atr * 3.0)
                    
                    active_trade = {
                        'time': ts, 'dir': signal_dir, 'entry': entry_price,
                        'sl': sl, 'tp': tp, 'status': 'OPEN', 'score': score
                    }
                    self.trades.append(active_trade)

        self.report()

    def close_trade(self, trade):
        pips = (trade['exit_price'] - trade['entry']) if trade['dir'] == 'LONG' else (trade['entry'] - trade['exit_price'])
        trade['pnl'] = pips * 10000
        self.balance += trade['pnl']

    def report(self):
        df_trades = pd.DataFrame(self.trades)
        if df_trades.empty:
            print("No trades executed.")
            return
            
        closed_trades = df_trades[df_trades['status'] != 'OPEN']
        if closed_trades.empty:
            print("No trades closed.")
            return
            
        win_rate = len(closed_trades[closed_trades['status']=='TP']) / len(closed_trades) * 100
        total_pnl = closed_trades['pnl'].sum()
        
        print("\n--- OPTIMIZED SCALP RESULTS ---")
        print(f"Total Trades: {len(closed_trades)}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Total PNL (Pips): {total_pnl:.2f}")
        print(f"Final Balance: ${self.balance:.2f}")
        
        df_trades.to_csv('scalp_backtest_results.csv')
        print("Results saved to 'scalp_backtest_results.csv'")

if __name__ == "__main__":
    print("\n--- RUNNING WITH 0 COSTS TO COMPARE ---")
    tester_no_cost = ScalpBacktest('eurusd_5m.csv', spread_pips=0, slippage_pips=0)
    tester_no_cost.run()
    
    print("\n--- RUNNING WITH REALISTIC COSTS (1.5 PIPS) ---")
    tester_real = ScalpBacktest('eurusd_5m.csv', spread_pips=1.5, slippage_pips=0.2)
    tester_real.run()
