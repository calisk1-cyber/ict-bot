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

        # Pure ICT Bias (Using SMC Market Structure)
        from ict_utils import get_smc_bias
        
        # Calculate bias on 1H timeframe
        df_1h['BIAS'] = df_1h.apply(lambda x: get_smc_bias(df_1h.loc[:x.name].tail(20)), axis=1)
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

            # Signal Score Calculation
            w = self.weights
            score = 0
            if row.get('FVG_Bull'): score += w.get('fvg', 25)
            if row.get('TurtleSoup_Bull'): score += w.get('turtle_soup', 20)
            if row.get('IFVG_Bull'): score += w.get('ifvg', 22)
            
            if row.get('FVG_Bear'): score -= w.get('fvg', 25)
            if row.get('TurtleSoup_Bear'): score -= w.get('turtle_soup', 20)
            if row.get('IFVG_Bear'): score -= w.get('ifvg', 22)

            # Pure ICT Filters: Kill Zones & PD Arrays
            is_kill_zone = (ts.hour in [7, 8, 9, 13, 14, 15, 18, 19])
            
            # Premium/Discount check (Dealing Range of last 50 bars)
            low_50 = df_5m['Low'].iloc[i-50:i].min()
            high_50 = df_5m['High'].iloc[i-50:i].max()
            midpoint = (low_50 + high_50) / 2
            is_discount = row['Close'] < midpoint
            is_premium = row['Close'] > midpoint
            
            # Adjusted to 30 for performance audit (Pure ICT) + Time/Space Filters
            if score >= 30 and row['BIAS'] == "BULLISH" and is_kill_zone and is_discount:
                self.open_trade(ticker, 'LONG', row, ts, pip_size, score)
                active_trade = self.trades[-1]
            elif score <= -30 and row['BIAS'] == "BEARISH" and is_kill_zone and is_premium: 
                self.open_trade(ticker, 'SHORT', row, ts, pip_size, score)
                active_trade = self.trades[-1]

    def open_trade(self, ticker, direction, row, ts, pip_size, score):
        # SMC/ICT Style: Stop loss at the low/high of the signal candle or the FVG pattern candle
        # For simplicity in this backtest, we use a structural offset based on the candles
        # If no specific structural info, fallback to a safe distance
        
        entry = row['Close']
        if direction == 'LONG':
            # SL below the recent 3-candle low (FVG area)
            sl = row['Low'] * 0.9995 # ~5-10 pips below
        else:
            # SL above the recent 3-candle high
            sl = row['High'] * 1.0005
            
        sl_dist = abs(entry - sl)
        if sl_dist < 0.0005: sl_dist = 0.0015 # Minimum safe distance
        
        tp = entry + (sl_dist * 3) if direction == 'LONG' else entry - (sl_dist * 3) # 1:3 RR is more realistic
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
