import pandas as pd
import numpy as np
import time
from oanda_data import download_oanda_candles
from ict_utils import (
    get_smc_bias_v11, apply_ict_v18_omniscient, 
    calculate_ote_v15
)

def calculate_sharpe(returns):
    if len(returns) < 2: return 0
    return (np.mean(returns) / np.std(returns)) * np.sqrt(252)

class FebruaryFullAudit:
    def __init__(self):
        self.initial_balance = 100000.0 # Standard Institutional Kasa
        self.balance = 100000.0
        self.trades_log = []
        self.all_returns = []
        # ELITE PORTFOLIO ONLY (Pruned based on Audit)
        self.symbols = ["USD_JPY", "XAU_USD", "USD_CAD"]

    def run(self):
        print("\n" + "="*60)
        print(" SINGULARITY V18 - FEBRUARY 2024 (1% RISK AUDIT) ")
        print("="*60)
        
        from_t = "2024-02-01T00:00:00Z"
        to_t = "2024-03-01T00:00:00Z"
        
        risk_per_trade = 1000.0 # 1% of 100k
        
        portfolio_stats = []

        for sym in self.symbols:
            print(f"\n--- Analiz Ediliyor: {sym} ---")
            df_5m = download_oanda_candles(sym, "M5", from_time=from_t, to_time=to_t)
            df_1h = download_oanda_candles(sym, "H1", from_time=from_t, to_time=to_t)
            
            if df_5m.empty:
                print(f"!! {sym} verisi çekilemedi.")
                continue
                
            print(f"-> {len(df_5m)} mum çekildi. V18 motoru çalıştırılıyor...")
            df_v18 = apply_ict_v18_omniscient(df_5m)
            df_1h['HTF_Bias'] = [get_smc_bias_v11(df_1h.iloc[:i+1].tail(20)) for i in range(len(df_1h))]
            df_v18 = pd.merge_asof(df_v18.sort_index(), df_1h[['HTF_Bias']].sort_index(), left_index=True, right_index=True)

            sym_trades = 0
            active_trade = None
            
            for i in range(100, len(df_v18) - 30):
                row = df_v18.iloc[i]
                if active_trade:
                    hit_sl, hit_tp = False, False
                    if active_trade['type'] == "BUY":
                        hit_sl, hit_tp = row['Low'] <= active_trade['sl'], row['High'] >= active_trade['tp']
                    else:
                        hit_sl, hit_tp = row['High'] >= active_trade['sl'], row['Low'] <= active_trade['tp']
                    
                    if hit_sl or hit_tp:
                        p_price = active_trade['sl'] if hit_sl else active_trade['tp']
                        # Calculate Risk Amount ($1000 per trade)
                        # pnl_usd = (p_price - entry) / (sl - entry) * risk_per_trade
                        pnl_ratio = (p_price - active_trade['entry']) / (active_trade['sl'] - active_trade['entry'])
                        pnl_usd = -(pnl_ratio * 1000.0) - 2.5 # $2.5 comm
                        
                        self.balance += pnl_usd
                        self.all_returns.append(pnl_usd)
                        sym_trades += 1
                        
                        outcome = "TP" if pnl_usd > 0 else "SL"
                        print(f"   [{sym} {active_trade['type']}] {active_trade['time']} -> {outcome} ({pnl_usd:+.2f}$)")
                        active_trade = None
                    continue

                if not row['is_algo_window']: continue
                bias = row['HTF_Bias']
                is_bull = row['CISD_Bull'] and "BULLISH" in bias
                is_bear = row['CISD_Bear'] and "BEARISH" in bias
                
                if is_bull or is_bear:
                    ote = calculate_ote_v15(row['High'], row['Low'], "BUY" if is_bull else "SELL")
                    dist = 2.0 if "XAU" in sym else 0.0012
                    sl = (ote - dist) if is_bull else (ote + dist)
                    tp = ote + (ote - sl) * 1.8
                    active_trade = {"type": "BUY" if is_bull else "SELL", "entry": ote, "sl": sl, "tp": tp, "time": row.name}
            
            time.sleep(0.5)

        self.final_report()

    def final_report(self):
        if not self.all_returns:
            print("No trades found across portfolio.")
            return

        df = pd.Series(self.all_returns)
        net = self.balance - self.initial_balance
        wr = (len(df[df > 0]) / len(df)) * 100
        sharpe = calculate_sharpe(df)
        pf = abs(df[df > 0].sum() / df[df <= 0].sum()) if len(df[df <= 0]) > 0 else 100
        mdd = (df.cumsum().expanding().max() - df.cumsum()).max()
        
        print("\n" + "="*60)
        print(" FINAL FEBRUARY PORTFOLIO AUDIT SUMMARY ")
        print("="*60)
        print(f" TOTAL TRADES: {len(df)}")
        print(f" WIN RATE: {wr:.1f}%")
        print(f" PROFIT FACTOR: {pf:.2f}")
        print(f" SHARPE RATIO: {sharpe:.2f}")
        print(f" MAX DRAWDOWN: ${mdd:.2f}")
        print(f" NET PORTFOLIO PnL: ${net:.2f}")
        print("="*60 + "\n")

if __name__ == "__main__":
    audit = FebruaryFullAudit()
    audit.run()
