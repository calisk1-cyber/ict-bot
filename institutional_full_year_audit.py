import pandas as pd
import numpy as np
import random
from datetime import datetime, timezone, timedelta
from oanda_data import download_oanda_candles
from ict_utils import apply_ict_v18_omniscient, get_smc_bias_v11
import time
import os

# --- V18 INSTITUTIONAL 1-YEAR BACKTESTER ---
# This script uses the exact Ultra-Stabil parameters:
# 1. Correct Units Calculation (JPY, GOLD, FX)
# 2. Institutional Spread & Slippage
# 3. 1:2.5 R/R Ratio (Recalibrated for Cost Neutralization)

class FullYearInstitutionalBacktester:
    def __init__(self, initial_balance=100000):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.trades = []
        
        # Institutional Costs (Average Real-World)
        self.SPREADS = {"EUR_USD": 0.00008, "GBP_USD": 0.00012, "XAU_USD": 0.35, "USD_JPY": 0.008, "USD_CAD": 0.00015}
        self.COMMISSION_PER_LOT = 7.0 
        
        self.symbol_meta = {
            "EUR_USD": {"pip": 0.0001, "jpy": False},
            "GBP_USD": {"pip": 0.0001, "jpy": False},
            "XAU_USD": {"pip": 0.1, "jpy": False},
            "USD_JPY": {"pip": 0.01, "jpy": True},
            "USD_CAD": {"pip": 0.0001, "jpy": False}
        }

    def calculate_units(self, ticker, entry, sl, risk_usd):
        sl_dist = abs(entry - sl)
        if sl_dist == 0: return 0
        if "XAU" in ticker:
            return int(risk_usd / sl_dist)
        elif "JPY" in ticker:
            # Proper USD/JPY Units Math
            return int(risk_usd / (sl_dist / entry))
        else:
            return int(risk_usd / sl_dist)

    def run_simulation(self, ticker, start_date, end_date):
        print(f"\n[AUDIT] Fetching data for {ticker} ({start_date} to {end_date})...")
        
        try:
            # We use Oanda's Factory via download_oanda_candles to handle 1 year of M5 data (~105k candles)
            df = download_oanda_candles(ticker, "M5", from_time=f"{start_date}T00:00:00Z", to_time=f"{end_date}T00:00:00Z")
            
            if df.empty:
                print(f"  Warning: No data found for {ticker}")
                return
            
            print(f"  Processing {len(df)} candles...")
            df = apply_ict_v18_omniscient(df)
            
            # Fetch H1 for correct Bias alignment
            print(f"  Fetching H1 data for Precise Bias...")
            df_h1 = download_oanda_candles(ticker, "H1", from_time=f"{start_date}T00:00:00Z", to_time=f"{end_date}T00:00:00Z")
            
            # Map H1 Bias to M5 rows (Aligning to the latest available H1 candle)
            print(f"  Mapping HTF Bias to M5 timeframe...")
            df['HTF_Bias'] = "NEUTRAL"
            if not df_h1.empty:
                # Calculate bias for each H1 candle
                h1_biases = []
                for j in range(len(df_h1)):
                    window = df_h1.iloc[max(0, j-20):j+1]
                    h1_biases.append(get_smc_bias_v11(window))
                df_h1['calculated_bias'] = h1_biases
                
                # Merge M5 with H1 bias
                df = pd.merge_asof(df.sort_index(), df_h1[['calculated_bias']].sort_index(), left_index=True, right_index=True, direction='backward')
                df.rename(columns={'calculated_bias': 'HTF_Bias'}, inplace=True)
            
            active_trade = None
            spread_points = self.SPREADS.get(ticker, 0.0002)
            meta = self.symbol_meta[ticker]
            
            for i in range(len(df)-1):
                row = df.iloc[i]
                next_row = df.iloc[i+1]
                
                if active_trade:
                    # Check SL/TP
                    if active_trade['side'] == "BUY":
                        if next_row['Low'] <= active_trade['sl']:
                            self.close_trade(active_trade, active_trade['sl'], "SL")
                            active_trade = None
                        elif next_row['High'] >= active_trade['tp']:
                            self.close_trade(active_trade, active_trade['tp'], "TP")
                            active_trade = None
                    else:
                        if next_row['High'] >= active_trade['sl']:
                            self.close_trade(active_trade, active_trade['sl'], "SL")
                            active_trade = None
                        elif next_row['Low'] <= active_trade['tp']:
                            self.close_trade(active_trade, active_trade['tp'], "TP")
                            active_trade = None
                    continue

                # Signal Detection
                if not row.get('is_algo_window'): continue
                
                bias = row.get('HTF_Bias', 'NEUTRAL')
                is_bull = row.get('CISD_Bull', False) and bias == "BULLISH"
                is_bear = row.get('CISD_Bear', False) and bias == "BEARISH"
                
                if is_bull or is_bear:
                    slip = random.uniform(0.3, 0.8) * meta['pip']
                    entry_p = next_row['Open'] + (spread_points/2) + slip if is_bull else next_row['Open'] - (spread_points/2) - slip
                    
                    # 1:2.5 RR recalibration
                    sl_dist = 25 * meta['pip']
                    sl = entry_p - sl_dist if is_bull else entry_p + sl_dist
                    tp = entry_p + (entry_p - sl) * 2.5
                    
                    units = self.calculate_units(ticker, entry_p, sl, self.balance * 0.01)
                    active_trade = {"side": "BUY" if is_bull else "SELL", "entry": entry_p, "sl": sl, "tp": tp, "units": units}
        except Exception as e:
            print(f"Error on {ticker}: {e}")

    def close_trade(self, trade, close_p, reason):
        pnl_raw = (close_p - trade['entry']) * trade['units'] if trade['side'] == "BUY" else (trade['entry'] - close_p) * trade['units']
        comm = (abs(trade['units']) / 100000.0) * self.COMMISSION_PER_LOT
        self.balance += (pnl_raw - comm)
        self.trades.append({"pnl": pnl_raw - comm, "reason": reason})

    def report(self):
        df_trades = pd.DataFrame(self.trades)
        if df_trades.empty:
            print("No trades executed.")
            return
        win_rate = (len(df_trades[df_trades['pnl'] > 0]) / len(df_trades)) * 100
        print(f"\n==================================================")
        print(f"   V18 INSTITUTIONAL 1-YEAR AUDIT (2025)")
        print(f"==================================================")
        print(f"Total Trades: {len(df_trades)}")
        print(f"Win Rate:     {win_rate:.1f}%")
        print(f"Final Balance: ${self.balance:.2f}")
        print(f"Net Profit:   ${self.balance - self.initial_balance:.2f}")
        print(f"==================================================\n")

if __name__ == "__main__":
    tester = FullYearInstitutionalBacktester()
    symbols = ["EUR_USD", "XAU_USD", "USD_JPY"]
    for s in symbols:
        tester.run_simulation(s, "2025-01-01", "2025-12-31")
    tester.report()
