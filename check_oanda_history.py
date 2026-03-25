import os
import oandapyV20
import oandapyV20.endpoints.trades as trades
import oandapyV20.endpoints.accounts as accounts
from dotenv import load_dotenv
import json

load_dotenv()

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")

client = oandapyV20.API(access_token=OANDA_API_KEY, environment=OANDA_ENV)

print(f"--- OANDA HESAP OZETI ({OANDA_ACCOUNT_ID}) ---")
r_acc = accounts.AccountSummary(accountID=OANDA_ACCOUNT_ID)
client.request(r_acc)
acc = r_acc.response.get('account', {})
print(f"Bakiye: {acc.get('balance')}")
print(f"Acik Pozisyon Sayisi: {acc.get('openPositionCount')}")

print("\n--- SON 10 ISLEM ---")
params = {"state": "ALL", "count": 10}
r_trades = trades.TradesList(accountID=OANDA_ACCOUNT_ID, params=params)
client.request(r_trades)

transactions = r_trades.response.get('trades', [])
for t in transactions:
    # Bazen realizedPL alanı olmayabilir veya farklı bir isimde olabilir
    pl = t.get('realizedPL', '0.00')
    time_str = t.get('openTime', 'Bilinmiyor')
    print(f"Tarih: {time_str} | ID: {t['id']} | Enstruman: {t['instrument']} | Unit: {t['initialUnits']} | Durum: {t['state']} | PnL: {pl}")

if not transactions:
    print("Islem bulunamadi.")
