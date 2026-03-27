import pandas as pd
import numpy as np
import os
import pandas_ta as ta
import json
from datetime import datetime

class ProfessionalBacktesterV8:
    def __init__(self, initial_balance=10000.0, max_trades=500):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.trades = []
        self.max_trades = max_trades
        self.weights = {"fvg": 20, "turtle_soup": 25, "ifvg": 15, "sb": 30, "macro": 20}
        
        if os.path.exists("optimized_weights.json"):
            try:
                with open("optimized_weights.json", "r") as f:
                    self.weights = json.load(f)
            except: pass

    def get_pip_value(self, ticker):
        if "USD" in ticker: return 0.0001
        if "XAU" in ticker: return 0.10
        if "NAS" in ticker or "US30" in ticker: return 1.0
        return 0.0001

    def run_backtest(self, ticker):
        if len(self.trades) >= self.max_trades: return
        
        file_5m = f"backtest_data/{ticker}_5m.csv"
        file_1h = f"backtest_data/{ticker}_1h.csv"
        if not os.path.exists(file_5m): return

        df_5m = pd.read_csv(file_5m, index_col=0, parse_dates=True)
        df_1h = pd.read_csv(file_1h, index_col=0, parse_dates=True)
        pip_size = self.get_pip_value(ticker)

        # Bias
        df_1h['EMA20'] = ta.ema(df_1h['Close'], length=20)
        df_1h['BIAS'] = "NEUTRAL"
        df_1h.loc[df_1h['Close'] > df_1h['EMA20'], 'BIAS'] = "BULLISH"
        df_1h.loc[df_1h['Close'] < df_1h['EMA20'], 'BIAS'] = "BEARISH"
        df_5m = pd.merge_asof(df_5m.sort_index(), df_1h[['BIAS']].sort_index(), left_index=True, right_index=True)

        # Indicators (Staging check)
        if os.getenv("STAGING") == "1":
            from ict_utils_experimental import find_fvg_v3, find_turtle_soup_v2, find_ifvg
        else:
            from ict_utils import find_fvg_v3, find_turtle_soup_v2, find_ifvg
            
        df_5m = find_fvg_v3(df_5m)
        df_5m = find_turtle_soup_v2(df_5m)
        df_5m = find_ifvg(df_5m)
        df_5m['ATR'] = ta.atr(df_5m['High'], df_5m['Low'], df_5m['Close'], length=14)
        
        active_trade = None
        for i in range(50, len(df_5m)):
            if len(self.trades) >= self.max_trades: break
            ts = df_5m.index[i]
            row = df_5m.iloc[i]
            
            if active_trade:
                is_long = active_trade['dir'] == 'LONG'
                if (is_long and row['Low'] <= active_trade['sl']) or (not is_long and row['High'] >= active_trade['sl']):
                    self.close_trade(active_trade, active_trade['sl'], ts, "SL")
                    active_trade = None
                elif (is_long and row['High'] >= active_trade['tp']) or (not is_long and row['Low'] <= active_trade['tp']):
                    self.close_trade(active_trade, active_trade['tp'], ts, "TP")
                    active_trade = None
                elif not active_trade['partial']:
                    # Strategy D: 2R Partial
                    risk = abs(active_trade['entry'] - active_trade['sl_orig'])
                    if (is_long and row['High'] >= active_trade['entry'] + 2*risk) or \
                       (not is_long and row['Low'] <= active_trade['entry'] - 2*risk):
                        self.balance += (active_trade['units'] * 0.5) * (2*risk)
                        active_trade['sl'] = active_trade['entry'] # BE
                        active_trade['partial'] = True
                continue

            # Signal
            is_sb = (ts.hour in [7, 14, 18])
            w = self.weights
            score = 0
            if row.get('FVG_Bull'): score += w.get('fvg', 20)
            if row.get('TurtleSoup_Bull'): score += w.get('turtle_soup', 25)
            if is_sb: score += w.get('sb', 30)
            
            # Reverted to 50 (Institutional Gold Standard)
            if score >= 50 and row['BIAS'] != "BEARISH":
                self.open_trade(ticker, 'LONG', row, ts, pip_size, score)
                active_trade = self.trades[-1]
            elif score <= -50 and row['BIAS'] != "BULLISH": 
                self.open_trade(ticker, 'SHORT', row, ts, pip_size, score)
                active_trade = self.trades[-1]

    def open_trade(self, ticker, direction, row, ts, pip_size, score):
        atr = row.get('ATR', 0.0010)
        sl_dist = atr * 2
        if sl_dist == 0: sl_dist = 0.0015
        entry = row['Close']
        sl = entry - sl_dist if direction == 'LONG' else entry + sl_dist
        tp = entry + (sl_dist * 5) if direction == 'LONG' else entry - (sl_dist * 5)
        units = (self.balance * 0.01) / sl_dist
        self.trades.append({
            'ticker': ticker, 'dir': direction, 'entry': entry, 'sl': sl, 'sl_orig': sl, 'tp': tp, 
            'units': units, 'partial': False, 'status': 'OPEN', 'time': ts, 'score': score, 'pnl': 0
        })

    def close_trade(self, trade, price, ts, status):
        trade['status'] = status
        u = trade['units'] * 0.5 if trade['partial'] else trade['units']
        pnl = (price - trade['entry']) * u if trade['dir'] == 'LONG' else (trade['entry'] - price) * u
        trade['pnl'] += pnl
        trade['exit_price'] = price
        trade['exit_time'] = ts
        self.balance += pnl

    def calculate_metrics(self):
        if not self.trades: return {"status": "NO_TRADES", "performance": {}}
        df = pd.DataFrame(self.trades)
        df = df[df['status'] != 'OPEN']
        if df.empty: return {"status": "NO_CLOSED_TRADES", "performance": {}}
        
        pnls = df['pnl'].values
        win_rate = (len(df[df['pnl'] > 0]) / len(df)) * 100
        net_pnl = self.balance - self.initial_balance
        
        balance_history = np.cumsum(np.insert(pnls, 0, self.initial_balance))
        peak = np.maximum.accumulate(balance_history)
        drawdown = (peak - balance_history) / (peak + 1e-9)
        max_dd = np.max(drawdown) * 100
        
        sharpe = np.mean(pnls) / (np.std(pnls) + 1e-9) * np.sqrt(252)
        
        return {
            "status": "SUCCESS",
            "performance": {
                "win_rate": float(win_rate), "net_pnl": float(net_pnl), "max_dd": float(max_dd), 
                "sharpe": float(sharpe), "total_trades": int(len(df))
            }
        }

if __name__ == "__main__":
    bt = ProfessionalBacktesterV8(max_trades=500)
    for t in ["EUR_USD", "XAU_USD", "NAS100_USD"]:
        bt.run_backtest(t)
    metrics = bt.calculate_metrics()
    
    # Save to experiments
    if os.path.exists("backtest_experiments.json"):
        try:
            with open("backtest_experiments.json", "r") as f:
                exps = json.load(f)
        except: exps = []
    else: exps = []
    
    # Standardized entry
    new_entry = {
        "timestamp": datetime.now().isoformat(),
        "status": metrics.get("status"),
        "performance": metrics.get("performance", {}),
        "params": bt.weights
    }
    exps.append(new_entry)
    with open("backtest_experiments.json", "w") as f:
        json.dump(exps, f, indent=4)
    
    # Print for app.py capture
    print(json.dumps(new_entry, indent=4))
