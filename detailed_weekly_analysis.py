import os
import oandapyV20
import oandapyV20.endpoints.trades as trades
import oandapyV20.endpoints.accounts as accounts
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

load_dotenv()

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")

client = oandapyV20.API(access_token=OANDA_API_KEY, environment=OANDA_ENV)

def calculate_sharpe(returns):
    if len(returns) < 2:
        return 0.0
    mean_return = np.mean(returns)
    std_return = np.std(returns)
    if std_return == 0:
        return 0.0
    # Annualized Sharpe (assuming daily returns, 252 trading days)
    return (mean_return / std_return) * np.sqrt(252)

def perform_analysis():
    print(f"--- HAFTALIK DETAYLI ANALİZ BAŞLATILIYOR ---")
    
    # 1. Fetch closed trades for the last 30 days
    # Oanda TradesList doesn't have a direct 'since' param easily for history, 
    # but we can fetch last 500 trades to be sure.
    params = {"state": "CLOSED", "count": 500}
    r_trades = trades.TradesList(accountID=OANDA_ACCOUNT_ID, params=params)
    client.request(r_trades)
    all_trades = r_trades.response.get('trades', [])
    
    if not all_trades:
        print("İşlem verisi bulunamadı.")
        return

    data = []
    for t in all_trades:
        data.append({
            'ID': t['id'],
            'OpenTime': pd.to_datetime(t['openTime']),
            'CloseTime': pd.to_datetime(t['closeTime']),
            'Symbol': t['instrument'],
            'PnL': float(t.get('realizedPL', 0)),
            'Units': abs(float(t['initialUnits']))
        })
    
    df = pd.DataFrame(data)
    
    # Range for "Extended Week" (Starts Thursday April 09, 2026)
    start_of_week = pd.Timestamp("2026-04-09").tz_localize('UTC')
    today = pd.Timestamp.now(tz='UTC')
    
    # Filter for extended week
    weekly_df = df[df['CloseTime'] >= start_of_week]
    
    # Filter for last 30 days (for Sharpe)
    start_30d = today - timedelta(days=30)
    month_df = df[df['CloseTime'] >= start_30d]
    
    # --- Weekly Metrics ---
    total_trades = len(weekly_df)
    wins = weekly_df[weekly_df['PnL'] > 0]
    losses = weekly_df[weekly_df['PnL'] <= 0]
    
    total_pnl = weekly_df['PnL'].sum()
    total_wins = wins['PnL'].sum()
    total_losses = losses['PnL'].sum()
    
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
    profit_factor = abs(total_wins / total_losses) if total_losses != 0 else float('inf')
    
    # --- Sharpe Ratio Calculation ---
    # Group by date for daily returns
    daily_returns = month_df.copy()
    daily_returns['Date'] = daily_returns['CloseTime'].dt.date
    daily_pnl = daily_returns.groupby('Date')['PnL'].sum()
    
    # We need to consider the initial balance for return percentage, 
    # but since it's a practice account we can use nominal PnL divided by a baseline (e.g. 100k)
    baseline_balance = 100000.0
    daily_return_pct = daily_pnl / baseline_balance
    sharpe = calculate_sharpe(daily_return_pct)
    
    # --- Display Results ---
    print("\n" + "="*40)
    print(f"HAFTALIK PERFORMANS ÖZETİ (13 - 15 Nisan)")
    print("="*40)
    print(f"Toplam İşlem Sayısı: {total_trades}")
    print(f"Başarı Oranı (WR): %{win_rate:.2f}")
    print(f"Toplam Net Kâr: {total_pnl:+.2f} USD")
    print(f"Toplam Kazanç: {total_wins:+.2f} USD")
    print(f"Toplam Kayıp: {total_losses:+.2f} USD")
    print(f"Profit Factor: {profit_factor:.2f}")
    print(f"Sharpe Ratio (30 Günlük): {sharpe:.2f}")
    print("-" * 40)
    
    # Detailed Table for Weekly Trades
    if not weekly_df.empty:
        print("\nBu Haftaki İşlemler:")
        print(weekly_df[['CloseTime', 'Symbol', 'PnL']].sort_values(by='CloseTime', ascending=False).to_string(index=False))
    
    # Save to a report file
    with open("weekly_detailed_report.md", "w", encoding="utf-8") as f:
        f.write("# Detaylı Haftalık Performans Analizi\n\n")
        f.write(f"**Dönem:** 13 Nisan 2026 - 15 Nisan 2026\n")
        f.write(f"**Analiz Tarihi:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## 📈 Ana Metrikler\n")
        f.write(f"- **Toplam İşlem:** {total_trades}\n")
        f.write(f"- **Win Rate:** %{win_rate:.1f}\n")
        f.write(f"- **Net PnL:** {total_pnl:+.2f} USD\n")
        f.write(f"- **Profit Factor:** {profit_factor:.2f}\n")
        f.write(f"- **Sharpe Oranı:** {sharpe:.2f} (Son 30 gün bazlı)\n\n")
        
        f.write("## 💰 Kazanç/Kayıp Detayı\n")
        f.write(f"- **Brüt Kazanç:** {total_wins:+.2f} USD\n")
        f.write(f"- **Brüt Kayıp:** {total_losses:+.2f} USD\n\n")
        
        f.write("## 📅 İşlem Listesi\n")
        f.write("| Kapanış Zamanı | Sembol | PnL (USD) |\n")
        f.write("| :--- | :--- | :--- |\n")
        for _, row in weekly_df.sort_values(by='CloseTime', ascending=False).iterrows():
            f.write(f"| {row['CloseTime'].strftime('%Y-%m-%d %H:%M')} | {row['Symbol']} | {row['PnL']:+.2f} |\n")

if __name__ == "__main__":
    perform_analysis()
