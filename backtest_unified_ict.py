import pandas as pd
import numpy as np
import os
import sys
from datetime import timedelta

# Path setup
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ict_utils import find_turtle_soup, find_fvg_v3, is_silver_bullet_zone

class UnifiedICTBacktest:
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
        print("Calculating Unified ICT Indicators (SMC + PO3 + OTE)...")
        df = self.df.copy()
        
        # 1. SMC: FVG, Sweep, MSS
        df = find_fvg_v3(df)
        df = find_turtle_soup(df, lookback=20)
        
        # 2. PO3: Accumulation Detection
        df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
        df['ATR_SMA'] = df['ATR'].rolling(20).mean()
        df['Is_Accumulation'] = df['ATR'] < (df['ATR_SMA'] * 0.8)
        
        # 3. OTE: Fibonacci 0.618 - 0.79
        df['Swing_High'] = df['High'].rolling(20).max()
        df['Swing_Low'] = df['Low'].rolling(20).min()
        df['Swing_Range'] = df['Swing_High'] - df['Swing_Low']
        df['OTE_Low'] = df['Swing_Low'] + (df['Swing_Range'] * 0.618)
        df['OTE_High'] = df['Swing_Low'] + (df['Swing_Range'] * 0.79)
        
        # 4. Filter: Kill Zones (EST Based via UTC offset)
        # London: 07:00-10:00 UTC | NY: 13:00-16:00 UTC
        df['Is_KillZone'] = df.index.map(lambda x: (7 <= x.hour <= 10) or (13 <= x.hour <= 17))
        
        print(f"Starting Simulation with {len(df)} candles...")
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

            # --- ENTRY (SMC + PO3 + OTE Confluence) ---
            if not active_trade and now['Is_KillZone']:
                # Sequence Check: 
                # 1. Sweep in last 15 candles
                recent = df.iloc[i-15:i+1]
                has_sweep_bull = recent['TurtleSoup_Bull'].any()
                has_sweep_bear = recent['TurtleSoup_Bear'].any()
                
                # 2. OTE Zone in last 3 candles
                in_ote = (df.iloc[i-3:i+1]['Close'] >= df.iloc[i-3:i+1]['OTE_Low']).any() and \
                         (df.iloc[i-3:i+1]['Close'] <= df.iloc[i-3:i+1]['OTE_High']).any()
                
                # 3. FVG Confirmation now
                if has_sweep_bull and now['FVG_Bull'] and in_ote:
                    active_trade = self.open_trade(ts, 'LONG', now['Close'], 'PO3_OTE')
                elif has_sweep_bear and now['FVG_Bear'] and in_ote:
                    active_trade = self.open_trade(ts, 'SHORT', now['Close'], 'PO3_OTE')

        self.report()

    def open_trade(self, ts, direction, price, mode):
        # Strict 1:3 RR as per new ICT rules
        atr = self.df['Close'].iloc[-14:].diff().abs().mean() or 0.0005
        sl_dist = atr * 1.5
        tp_dist = sl_dist * 3.0
        
        sl = price - sl_dist if direction == 'LONG' else price + sl_dist
        tp = price + tp_dist if direction == 'LONG' else price - tp_dist
        entry = (price + self.spread/2) if direction == 'LONG' else (price - self.spread/2)
        return {'time': ts, 'dir': direction, 'entry': entry, 'sl': sl, 'tp': tp, 'status': 'OPEN', 'mode': mode}

    def close_trade(self, trade, price, ts, status):
        trade['status'] = status; trade['exit_price'] = price; trade['exit_time'] = ts
        pips = (price - trade['entry']) if trade['dir'] == 'LONG' else (trade['entry'] - price)
        trade['pnl'] = pips * 10000
        self.balance += (trade['pnl'] * 1.0) # 1 Lot
        self.trades.append(trade)

    def report(self):
        df = pd.DataFrame(self.trades)
        if df.empty: 
            print("No high-confluence trades found in 30 days. The filters are very strict.")
            return
        wr = len(df[df['status'] == 'TP']) / len(df) * 100
        print(f"\n--- UNIFIED ICT (PO3 + OTE + SMC) 30-DAY REPORT ---")
        print(f"Total Trades: {len(df)}")
        print(f"Win Rate: {wr:.2f}%")
        print(f"Total PNL: ${self.balance - 10000:.2f}")

if __name__ == "__main__":
    tester = UnifiedICTBacktest('eurusd_5m.csv')
    tester.run()
