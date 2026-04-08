import psycopg2
import os
import json
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from realistic_backtest_v8 import ProfessionalBacktesterV8
from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
ENVIRONMENT = os.getenv("OANDA_ENV", "practice")

class Gen2MasterAudit:
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL)
        self.tester = ProfessionalBacktesterV8(initial_balance=100000.0)
        self.real_balance = 100000.0
        self.all_trades = []
        self.spreads = {}

    def fetch_spread(self, ticker):
        if ticker in self.spreads: return self.spreads[ticker]
        try:
            client = API(access_token=API_KEY, environment=ENVIRONMENT)
            params = {"count": 10, "granularity": "M5", "price": "BA"}
            r = InstrumentsCandles(instrument=ticker, params=params)
            client.request(r)
            spreads = [float(c["ask"]["c"]) - float(c["bid"]["c"]) for c in r.response["candles"] if c["complete"]]
            s = np.mean(spreads) if spreads else 0.0002
            self.spreads[ticker] = s
            return s
        except: return 0.0002

    def calculate_real_pnl(self, ticker, raw_pnl, outcome, sl_dist):
        s = self.fetch_spread(ticker)
        pip_v = 10.0 if "USD" in ticker else 1.0
        pip_sz = 0.0001 if "USD" in ticker and "XAU" not in ticker and "NAS" not in ticker else 1.0
        if "JPY" in ticker: pip_sz = 0.01; pip_v = 10.0
        
        s_pips = s / pip_sz
        # Hard lot calculation for $1000 risk (FLAT)
        lots = (1000.0 / (sl_dist / pip_sz * pip_v)) if sl_dist > 0 else 0.1
        lots = max(lots, 0.01)
        
        cost = (s_pips * pip_v * lots) + (0.5 * pip_v * lots) + (3.5 * lots * 2)
        return raw_pnl - cost

    def run(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, name, pairs FROM strategies WHERE id IN (SELECT strategy_id FROM backtest_results WHERE passed=True) LIMIT 400")
        strats = cur.fetchall()
        print(f"--- Üretilen {len(strats)} strateji denetleniyor ---")

        for s_id, s_name, s_pairs in strats:
            pair = s_pairs[0] if s_pairs else "EUR_USD"
            self.tester.run_backtest(pair)
            
            for t in self.tester.trades:
                if t['status'] in ['TP', 'SL']:
                    # FLAT RISK Audit ($1000 per trade)
                    sl_dist = abs(t['entry'] - t['sl_orig'])
                    raw_pnl = 3000.0 if t['status'] == "TP" else -1000.0
                    
                    real_pnl = self.calculate_real_pnl(pair, raw_pnl, t['status'], sl_dist)
                    
                    self.real_balance += real_pnl
                    self.all_trades.append({
                        "time": t['time'], "name": s_name, "pair": pair, "dir": t['dir'],
                        "raw_pnl": raw_pnl, "real_pnl": real_pnl, "status": t['status']
                    })
            
            if len(self.all_trades) >= 1200: break
            print(f"Strateji: {s_name[:30]}... | Toplam İşlem: {len(self.all_trades)}", end="\r")

        # Cleanup and results
        print("\n" + "="*40)
        print("GEN 2 MASTER AUDIT RESULTS (REALISTIC - FLAT RISK)")
        print("="*40)
        final_trades = self.all_trades[:1000]
        wins = [t for t in final_trades if t['status'] == 'TP']
        wr = (len(wins)/len(final_trades))*100
        raw_final = sum(t['raw_pnl'] for t in final_trades) + 100000
        real_final = sum(t['real_pnl'] for t in final_trades) + 100000
        
        print(f"Toplam İşlem: {len(final_trades)}")
        print(f"Win Rate: {wr:.2f}%")
        print(f"Teorik Bakiye: ${raw_final:,.2f}")
        print(f"Gerçekçi Bakiye: ${real_final:,.2f}")
        print(f"Net Kar: ${ (real_final - 100000):,.2f}")
        
        # Log to file
        with open("gen2_master_audit_log.txt", "w") as f:
            for t in final_trades:
                f.write(f"{t['time']} | {t['pair']} | {t['dir']} | Raw:{t['raw_pnl']:.2f} | Real:{t['real_pnl']:.2f} | {t['status']}\n")

if __name__ == "__main__":
    audit = Gen2MasterAudit()
    audit.run()
