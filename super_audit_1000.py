import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timedelta
from realistic_backtest_v8 import ProfessionalBacktesterV8
from ict_utils import download_full_history, find_fvg_v3, find_turtle_soup_v2, find_ifvg, get_smc_bias

class MasterAuditPortfolio:
    def __init__(self, pairs=None):
        self.pairs = pairs or ["EUR_USD", "GBP_USD", "XAU_USD", "NAS100_USD", "USD_JPY", 
                              "AUD_USD", "USD_CAD", "EUR_JPY", "GBP_JPY", "BTC_USD",
                              "ETH_USD", "XAG_USD", "US30_USD", "SPX500_USD", "NZD_USD"]
        self.tester = ProfessionalBacktesterV8(initial_balance=100000.0, max_trades=5000)

    def run_on_pair(self, ticker):
        print(f"Auditing: {ticker}...")
        df = download_full_history(ticker, interval="5m", period="60d")
        if df.empty: return
        
        # HTF Bias from 1H
        df_1h = download_full_history(ticker, interval="1h", period="60d")
        if df_1h.empty: return
        df_1h['BIAS'] = df_1h.apply(lambda x: get_smc_bias(df_1h.loc[:x.name].tail(20)), axis=1)
        
        # Merge Bias
        df = pd.merge_asof(df.sort_index(), df_1h[['BIAS']].sort_index(), left_index=True, right_index=True)

        # Indicators
        df = find_fvg_v3(df)
        df = find_turtle_soup_v2(df)
        df = find_ifvg(df)
        
        pip_size = 0.0001
        active_trade = None
        
        for i in range(50, len(df)):
            ts = df.index[i]
            row = df.iloc[i]
            
            if active_trade:
                is_long = active_trade['dir'] == 'LONG'
                if (is_long and row['Low'] <= active_trade['sl']) or (not is_long and row['High'] >= active_trade['sl']):
                    self.tester.close_trade(active_trade, active_trade['sl'], ts, "SL")
                    active_trade = None
                elif (is_long and row['High'] >= active_trade['tp']) or (not is_long and row['Low'] <= active_trade['tp']):
                    self.tester.close_trade(active_trade, active_trade['tp'], ts, "TP")
                    active_trade = None
                continue

            # Loosened score for "Portfolio" flow
            score = 0
            w = self.tester.weights
            if row.get('FVG_Bull'): score += w.get('fvg', 25)
            if row.get('TurtleSoup_Bull'): score += w.get('turtle_soup', 20)
            if row.get('IFVG_Bull'): score += w.get('ifvg', 22)
            if row.get('FVG_Bear'): score -= w.get('fvg', 25)
            if row.get('TurtleSoup_Bear'): score -= w.get('turtle_soup', 20)
            if row.get('IFVG_Bear'): score -= w.get('ifvg', 22)

            if score >= 25 and row.get('BIAS') == "BULLISH":
                self.tester.open_trade(ticker, 'LONG', row, ts, pip_size, score)
                active_trade = self.tester.trades[-1]
            elif score <= -25 and row.get('BIAS') == "BEARISH":
                self.tester.open_trade(ticker, 'SHORT', row, ts, pip_size, score)
                active_trade = self.tester.trades[-1]

    def run(self):
        print(f"--- [PORTFOLIO MASTER] Starting 1000-Trade Quest ---")
        for p in self.pairs:
            self.run_on_pair(p)
            if len(self.tester.trades) >= 1000: break
            
        metrics = self.tester.calculate_metrics()
        self.save_report(metrics)
        return metrics

    def save_report(self, metrics):
        report_file = "master_1000_portfolio_log.txt"
        with open(report_file, "w") as f:
            f.write("="*50 + "\n")
            f.write("MASTER 1000-TRADE PORTFOLIO AUDIT (60D / 5M)\n")
            f.write("="*50 + "\n")
            f.write(json.dumps(metrics, indent=4) + "\n\n")
            f.write("--- FULL TRADE LOG ---\n")
            for t in self.tester.trades:
                f.write(f"{t['time']} | {t['ticker']} | {t['dir']} | PnL: {t['pnl']:.2f} | {t['status']}\n")
        print(f"Done. {len(self.tester.trades)} trades logged to {report_file}")

if __name__ == "__main__":
    audit = MasterAuditPortfolio()
    audit.run()
