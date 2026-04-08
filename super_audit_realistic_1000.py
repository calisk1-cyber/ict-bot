import pandas as pd
import numpy as np
import os
import json
import time
from datetime import datetime, timedelta
from realistic_backtest_v8 import ProfessionalBacktesterV8
from ict_utils import download_full_history, find_fvg_v3, find_turtle_soup_v2, find_ifvg, get_smc_bias
from dotenv import load_dotenv
import matplotlib.pyplot as plt

load_dotenv()
API_KEY = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
ENVIRONMENT = os.getenv("OANDA_ENV", "practice")

from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles

class SuperAuditRealistic:
    def __init__(self, pairs=None):
        self.pairs = pairs or ["EUR_USD", "GBP_USD", "XAU_USD", "NAS100_USD", "USD_JPY", "AUD_USD", "USD_CAD"]
        self.tester = ProfessionalBacktesterV8(initial_balance=100000.0, max_trades=2000)
        self.realistic_balance = 100000.0
        self.realistic_equity = [100000.0]
        self.trades = []
        
        self.broker_costs = {
            "EUR_USD": (1.2, 3.50, 0.3), "GBP_USD": (1.8, 3.50, 0.5),
            "XAU_USD": (25.0, 0.00, 1.5), "NAS100_USD": (150.0, 0.00, 8.0),
        }
        self.pip_values = {"EUR_USD": 10.0, "GBP_USD": 10.0, "XAU_USD": 1.0, "NAS100_USD": 1.0}

    def fetch_spread(self, ticker):
        try:
            client = API(access_token=API_KEY, environment=ENVIRONMENT)
            params = {"count": 20, "granularity": "M5", "price": "BA"}
            r = InstrumentsCandles(instrument=ticker, params=params)
            client.request(r)
            spreads = [float(c["ask"]["c"]) - float(c["bid"]["c"]) for c in r.response["candles"] if c["complete"]]
            return np.mean(spreads) if spreads else None
        except: return None

    def calculate_cost(self, ticker, raw_pnl, outcome, avg_spread, sl_pips):
        pip_v = self.pip_values.get(ticker, 10.0 if "USD" in ticker else 1.0)
        pip_sz = 0.0001 if "USD" in ticker and "XAU" not in ticker and "NAS" not in ticker else 1.0
        if "JPY" in ticker: pip_sz = 0.01; pip_v = 10.0
        
        fallback = self.broker_costs.get(ticker, (2.0, 3.50, 0.5))
        spread_pips = (avg_spread / pip_sz) if avg_spread else fallback[0]
        
        # Actual Lot calculation
        lots = (abs(raw_pnl) / (sl_pips * pip_v)) if sl_pips > 0 else 0.1
        lots = max(lots, 0.01)
        
        s_cost = spread_pips * pip_v * lots
        slip_cost = (fallback[2] * (1.5 if outcome == "SL" else 1.0)) * pip_v * lots
        comm_cost = fallback[1] * lots * 2
        return s_cost + slip_cost + comm_cost

    def run_on_pair(self, ticker):
        print(f"Auditing 1H {ticker}...")
        avg_spread = self.fetch_spread(ticker)
        df = download_full_history(ticker, interval="1h", period="730d")
        if df.empty: return

        df['BIAS'] = df.apply(lambda x: get_smc_bias(df.loc[:x.name].tail(100)), axis=1)
        df = find_fvg_v3(df); df = find_turtle_soup_v2(df); df = find_ifvg(df)

        active_trade = None
        pip_sz = 0.0001 if "USD" in ticker and "XAU" not in ticker and "NAS" not in ticker else 1.0
        if "JPY" in ticker: pip_sz = 0.01

        for i in range(50, len(df)):
            ts, row = df.index[i], df.iloc[i]
            if len(self.trades) >= 2000: break
            if self.realistic_balance <= 1000: break # Broke

            if active_trade:
                is_long = active_trade['dir'] == 'LONG'
                hit = None
                if (is_long and row['Low'] <= active_trade['sl']) or (not is_long and row['High'] >= active_trade['sl']): hit = "SL"
                elif (is_long and row['High'] >= active_trade['tp']) or (not is_long and row['Low'] <= active_trade['tp']): hit = "TP"
                
                if hit:
                    raw_pnl = (self.tester.balance * 0.03) if hit == "TP" else -(self.tester.balance * 0.01)
                    # Convert sl_dist to pips
                    sl_pips = active_trade['sl_dist'] / pip_sz
                    cost = self.calculate_cost(ticker, raw_pnl, hit, avg_spread, sl_pips)
                    real_pnl = raw_pnl - cost
                    self.tester.balance += raw_pnl
                    self.realistic_balance += real_pnl
                    self.trades.append({"ticker": ticker, "status": hit, "raw": raw_pnl, "real": real_pnl})
                    active_trade = None
                continue

            score = 0
            w = self.tester.weights
            if row.get('FVG_Bull'): score += w.get('fvg', 25)
            if row.get('TurtleSoup_Bull'): score += w.get('turtle_soup', 20)
            if row.get('IFVG_Bull'): score += w.get('ifvg', 22)
            if row.get('FVG_Bear'): score -= w.get('fvg', 25)
            if row.get('TurtleSoup_Bear'): score -= w.get('turtle_soup', 20)
            if row.get('IFVG_Bear'): score -= w.get('ifvg', 22)

            if (score >= 25 and row.get('BIAS') == "BULLISH") or (score <= -25 and row.get('BIAS') == "BEARISH"):
                direction = 'LONG' if score >= 25 else 'SHORT'
                # STRUCTURAL SL
                sl = row['Low'] * 0.9995 if direction == 'LONG' else row['High'] * 1.0005
                sl_dist = abs(row['Close'] - sl)
                if sl_dist < (pip_sz * 5): sl_dist = pip_sz * 10 # Min 10 pips
                tp = row['Close'] + (sl_dist * 3) if direction == 'LONG' else row['Close'] - (sl_dist * 3)
                active_trade = {'dir': direction, 'sl': sl, 'tp': tp, 'sl_dist': sl_dist}

    def run(self):
        for p in self.pairs:
            self.run_on_pair(p)
            if len(self.trades) >= 1000: break
        
        wins = [t for t in self.trades if t['status'] == 'TP']
        wr = (len(wins)/len(self.trades))*100 if self.trades else 0
        print(f"\n- DONE. Trades: {len(self.trades)}, Win Rate: {wr:.2f}%")
        print(f"- Theoretical Final: ${self.tester.balance:,.2f}")
        print(f"- Realistic Final: ${self.realistic_balance:,.2f}")

if __name__ == "__main__":
    audit = SuperAuditRealistic()
    audit.run()
