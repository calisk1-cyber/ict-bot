import os
import oandapyV20
import oandapyV20.endpoints.accounts as accounts
import oandapyV20.endpoints.pricing as pricing
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime

load_dotenv()

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")

client = oandapyV20.API(access_token=OANDA_API_KEY, environment=OANDA_ENV)

def check_active():
    print(f"--- AKTIF ISLEM DURUMU ---")
    
    # 1. Get Account Details (for unrealized PnL)
    r_acc = accounts.AccountDetails(accountID=OANDA_ACCOUNT_ID)
    client.request(r_acc)
    acc = r_acc.response.get('account', {})
    
    unrealized_pnl = float(acc.get('unrealizedPL', 0))
    balance = float(acc.get('balance', 0))
    
    print(f"Bakiye: {balance:.2f} USD")
    print(f"Toplam Bekleyen (Floating) Kar/Zarar: {unrealized_pnl:+.2f} USD")
    
    # 2. List Trades
    trades = acc.get('trades', [])
    if not trades:
        print("Açık işlem bulunamadı.")
        return

    data = []
    for t in trades:
        data.append({
            'ID': t['id'],
            'OpenTime': t['openTime'],
            'Symbol': t['instrument'],
            'Units': float(t['currentUnits']),
            'Entry': float(t['price']),
            'PnL': float(t['unrealizedPL'])
        })
    
    df = pd.DataFrame(data)
    df['OpenTime'] = pd.to_datetime(df['OpenTime'])
    
    print("\nAçık İşlemler Listesi:")
    print(df[['ID', 'Symbol', 'Units', 'Entry', 'PnL', 'OpenTime']].to_string(index=False))
    
    # Save to a report
    with open("active_trades_report.md", "w", encoding="utf-8") as f:
        f.write("# Aktif İşlem Raporu\n\n")
        f.write(f"**Tarih:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Toplam Floating PnL:** {unrealized_pnl:+.2f} USD\n\n")
        
        f.write("## 🔍 Açık Pozisyonlar\n")
        f.write("| ID | Sembol | Units | Giriş | Mevcut PnL |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for _, row in df.iterrows():
            f.write(f"| {row['ID']} | {row['Symbol']} | {row['Units']} | {row['Entry']:.5f} | {row['PnL']:+.2f} |\n")

if __name__ == "__main__":
    check_active()
