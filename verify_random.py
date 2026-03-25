import yfinance as yf
import pandas as pd
import numpy as np
import random

# Common setup from backtest_ict
INITIAL_BALANCE = 10000
RISK_PER_TRADE = 0.01 # %1 risk

def random_backtest(df, balance=10000):
    balance = balance
    trades = []
    equity_curve = [balance]
    
    # Simple ATR for SL/TP consistency
    df['ATR'] = df['High'].rolling(14).max() - df['Low'].rolling(14).min()
    df = df.dropna()
    
    for i in range(len(df)):
        if random.random() > 0.98: # ~%2 probability each hour
            direction = random.choice(['LONG', 'SHORT'])
            price = df['Close'].iloc[i]
            atr = df['ATR'].iloc[i]
            if atr <= 0: continue
            
            risk_amt = balance * RISK_PER_TRADE
            sl_dist = atr * 1.5 
            tp_dist = sl_dist * 1.5
            
            # Simulate randomly 1.5R
            win_prob = 0.4 # Theoretical for 1.5R
            is_win = random.random() < win_prob
            
            if is_win:
                pnl = risk_amt * 1.5
                trades.append(1)
            else:
                pnl = -risk_amt
                trades.append(0)
            
            balance += pnl
            equity_curve.append(balance)
            
    # Metrics
    win_rate = (sum(trades) / len(trades)) * 100 if trades else 0
    net_pnl = ((balance - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
    
    # Max DD
    peak = INITIAL_BALANCE
    max_dd = 0
    curr_bal = INITIAL_BALANCE
    for b in equity_curve:
        if b > peak: peak = b
        dd = (peak - curr_bal) / peak * 100 # Corrected logic
        curr_bal = b # Update curr_bal
        if dd > max_dd: max_dd = dd
        
    return net_pnl, win_rate, max_dd, len(trades)

# Load data (730d safe)
df = yf.download('EURUSD=X', start='2024-04-01', end='2025-03-01', interval='1h', progress=False)
if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)

pnl, wr, mdd, count = random_backtest(df)

print(f"--- RASTGELE BOT SONUCLARI (~1 YIL) ---")
print(f"Toplam Islem: {count}")
print(f"Net PnL     : %{pnl:.2f}")
print(f"Win Rate    : %{wr:.2f}")
print(f"Max DD      : %{mdd:.2f}")
