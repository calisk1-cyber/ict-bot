import pandas as pd
import numpy as np
import os
import pandas_ta as ta
import json
from datetime import datetime

class ProfessionalBacktesterV8:
    def __init__(self, initial_balance=10000, max_trades=5000, use_analyst=False):
        self.initial_balance = initial_balance
        self.balance = float(initial_balance)
        self.max_trades = max_trades
        self.use_analyst = use_analyst
        self.trades = []
        self.daily_pnls = []
        self.current_drawdown = 0.0
        self.high_water_mark = float(initial_balance)
        self.total_fees_saved = 0
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
        print(f"\n--- [BACKTEST] {ticker} (60-Day Audit) ---")
        from ict_utils import find_fvg_v3, find_turtle_soup_v2, find_ifvg, download_full_history, get_smc_bias
        
        # 1. Download 1H Data for Bias
        df_1h = download_full_history(ticker, interval="1h", period="60d")
        if df_1h.empty: return
        df_1h['BIAS'] = df_1h.apply(lambda x: get_smc_bias(df_1h.loc[:x.name].tail(20)), axis=1)
        
        # 2. Download 5M Data for Execution
        df_5m = download_full_history(ticker, interval="5m", period="60d")
        if df_5m.empty: return
        
        # 3. Merge Bias 1H -> 5M
        df_5m = pd.merge_asof(df_5m.sort_index(), df_1h[['BIAS']].sort_index(), left_index=True, right_index=True)
        
        # 4. Indicators & Enrichment
        df_5m = find_fvg_v3(df_5m)
        df_5m = find_turtle_soup_v2(df_5m)
        df_5m = find_ifvg(df_5m)
        
        # Experimental Staging Logic
        if os.getenv("STAGING") == "1":
            try:
                import ict_utils_experimental as experimental
                df_5m = experimental.find_new_logic(df_5m)
                print("[STAGING] Integrated Experimental Logic")
            except Exception as e:
                print(f"[STAGING ERROR] {e}")
        
        pip_size = self.get_pip_value(ticker)
        active_trade = None
        
        # 5. Trade Loop
        for i in range(50, len(df_5m)):
            if len(self.trades) >= self.max_trades: break
            ts = df_5m.index[i]
            row = df_5m.iloc[i]
            
            if active_trade:
                is_long = active_trade['dir'] == 'LONG'
                curr_price = row['Close']
                # Check SL
                if (is_long and row['Low'] <= active_trade['sl']) or (not is_long and row['High'] >= active_trade['sl']):
                    self.close_trade(active_trade, active_trade['sl'], ts, "SL")
                    active_trade = None
                # Check TP
                elif (is_long and row['High'] >= active_trade['tp']) or (not is_long and row['Low'] <= active_trade['tp']):
                    self.close_trade(active_trade, active_trade['tp'], ts, "TP")
                    active_trade = None
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

            # Premium/Discount check (Dealing Range)
            low_50 = df_5m['Low'].iloc[i-50:i].min()
            high_50 = df_5m['High'].iloc[i-50:i].max()
            midpoint = (low_50 + high_50) / 2
            is_discount = row['Close'] < midpoint
            is_premium = row['Close'] > midpoint
            
            # --- AGGRESSIVE SCALPER PIVOT (HFT MODE) ---
            # Lowering threshold from 35 to 20 for 10x more trades
            # Adding RSI as a fast scalper filter
            if 'RSI' not in df_5m.columns:
                df_5m['RSI'] = ta.rsi(df_5m['Close'], length=14)
                
            rsi = df_5m['RSI'].iloc[i]
            
            # --- BOT 5 ANALYST SIMULATION ---
            # 1. Dynamic Spread Watchdog (ATR-based volatility simulation)
            if 'ATR' not in df_5m.columns:
                df_5m['ATR'] = ta.atr(df_5m['High'], df_5m['Low'], df_5m['Close'], length=14)
            
            atr = df_5m['ATR'].iloc[i]
            avg_atr = df_5m['ATR'].rolling(50).mean().iloc[i] or atr
            is_high_vol = atr > (avg_atr * 1.5)
            
            # 2. Dynamic Risk Scaling
            risk_val = 1.0
            if self.use_analyst and self.current_drawdown > 0.10: 
                risk_val = 0.25 
            
            # 24/7 Scalper Logic (Aggressive Mode)
            # Threshold: 20 (Reduced from 35)
            # Conditions: Score + RSI Overbought/Oversold + HTF Bias
            if score >= 20 and row.get('BIAS') == "BULLISH" and rsi < 60:
                if self.use_analyst and is_high_vol:
                    self.total_fees_saved += 1
                    continue
                self.open_trade(ticker, 'LONG', row, ts, pip_size, score, risk_val)
                active_trade = self.trades[-1]
            elif score <= -20 and row.get('BIAS') == "BEARISH" and rsi > 40: 
                if self.use_analyst and is_high_vol:
                    self.total_fees_saved += 1
                    continue
                self.open_trade(ticker, 'SHORT', row, ts, pip_size, score, risk_val)
                active_trade = self.trades[-1]

    def open_trade(self, ticker, direction, row, ts, pip_size, score, risk_val=1.0):
        entry = row['Close']
        if direction == 'LONG':
            sl = row['Low'] * 0.9995 
        else:
            sl = row['High'] * 1.0005
            
        sl_dist = abs(entry - sl)
        if sl_dist < 0.0003: sl_dist = 0.0005 
        
        # SCALPER RR: 1:1.5
        tp = entry + (sl_dist * 1.5) if direction == 'LONG' else entry - (sl_dist * 1.5)
        # Apply risk_val from Analyst
        units = (self.balance * (0.01 * risk_val)) / sl_dist
        
        self.trades.append({
            'ticker': ticker, 'dir': direction, 'entry': entry, 'sl': sl, 'sl_orig': sl, 'tp': tp, 
            'units': units, 'partial': False, 'status': 'OPEN', 'time': ts, 'score': score, 'pnl': 0
        })

    def close_trade(self, trade, price, ts, status):
        trade['status'] = status
        u = trade['units'] * 0.5 if trade['partial'] else trade['units']
        
        # --- INSTITUTIONAL AUDIT: SPREAD & COMMISSION ---
        # 1. Spread Deduction (approx 0.7 pips per trade)
        spread_cost = 0.00007 * u if "JPY" not in trade['ticker'] else 0.007 * u
        if "XAU" in trade['ticker']: spread_cost = 0.20 * trade['units'] # $20 per 100oz (typical)
        
        # 2. Commission (approx $7 per 1.0 lot / 100k units round-turn)
        commission = (u / 100000) * 7.0
        
        # Raw PnL
        pnl = (price - trade['entry']) * u if trade['dir'] == 'LONG' else (trade['entry'] - price) * u
        
        # Final Net PnL after costs
        net_trade_pnl = pnl - spread_cost - commission
        
        trade['pnl'] = net_trade_pnl
        trade['exit_price'] = price
        trade['exit_time'] = ts
        self.balance += net_trade_pnl
        
        # Update high water mark and drawdown
        if self.balance > self.high_water_mark:
            self.high_water_mark = self.balance
        self.current_drawdown = (self.high_water_mark - self.balance) / self.high_water_mark

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
                "sharpe": float(sharpe), "total_trades": int(len(df)), "fees_saved": self.total_fees_saved
            }
        }

if __name__ == "__main__":
    symbols = ["EUR_USD", "GBP_USD", "XAU_USD", "NAS100_USD", "USD_JPY", "AUD_USD", "USD_CAD", "EUR_JPY"]
    
    print("\n" + "="*60)
    print("      A/B TEST: STANDARD SCALPER VS BOT 5 ANALYST")
    print("="*60)
    
    # MOD A: Standard Scalper (No Bot 5)
    bt_std = ProfessionalBacktesterV8(use_analyst=False)
    for t in symbols: bt_std.run_backtest(t)
    res_std = bt_std.calculate_metrics()["performance"]
    
    # MOD B: With Bot 5 Analyst (Spread & Risk scaling)
    bt_ai = ProfessionalBacktesterV8(use_analyst=True)
    for t in symbols: bt_ai.run_backtest(t)
    res_ai = bt_ai.calculate_metrics()["performance"]
    
    print(f"\n{'METRIC':<20} | {'STANDARD':<15} | {'BOT 5 AI':<15} | {'DIFF'}")
    print("-" * 65)
    print(f"{'Total Trades':<20} | {res_std['total_trades']:<15} | {res_ai['total_trades']:<15} | {res_ai['total_trades']-res_std['total_trades']}")
    print(f"{'Net PnL ($)':<20} | {res_std['net_pnl']:<15.2f} | {res_ai['net_pnl']:<15.2f} | {res_ai['net_pnl']-res_std['net_pnl']:.2f}")
    print(f"{'Max Drawdown (%)':<20} | {res_std['max_dd']:<15.2f} | {res_ai['max_dd']:<15.2f} | {res_ai['max_dd']-res_std['max_dd']:.2f}")
    print(f"{'Sharpe Ratio':<20} | {res_std['sharpe']:<15.2f} | {res_ai['sharpe']:<15.2f} | {res_ai['sharpe']-res_std['sharpe']:.2f}")
    print(f"{'High Spread Avoided':<20} | {'0':<15} | {res_ai['fees_saved']:<15} | +{res_ai['fees_saved']}")
    print("="*60)
