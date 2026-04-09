from oandapyV20 import API
import oandapyV20.endpoints.transactions as trans
import os
from dotenv import load_dotenv

load_dotenv(override=True)
api = API(access_token=os.getenv('OANDA_API_KEY'), environment=os.getenv('OANDA_ENV', 'practice'))
account_id = os.getenv('OANDA_ACCOUNT_ID')

def get_recent_fills():
    r = trans.TransactionList(account_id)
    api.request(r)
    last_id = int(r.response.get('lastTransactionID'))
    
    r2 = trans.TransactionsSinceID(account_id, params={'id': max(1, last_id - 100)})
    txs = api.request(r2)['transactions']
    
    print("=" * 70)
    print(f"{'Zaman':<20} | {'Parite':<10} | {'Islem':<10} | {'PnL ($)':<10}")
    print("-" * 70)
    
    total_pnl = 0
    for t in txs:
        if t['type'] == 'ORDER_FILL' and float(t.get('pl', 0)) != 0:
            ts = t['time'][:19].replace('T', ' ')
            inst = t.get('instrument', 'N/A')
            units = int(t.get('units', 0))
            pnl = float(t.get('pl', 0))
            total_pnl += pnl
            side = "KAPAMA (BUY)" if units > 0 else "KAPAMA (SELL)"
            print(f"{ts:<20} | {inst:<10} | {side:<12} | {pnl:+.2f}")
            
    print("-" * 70)
    print(f"Toplam Gerceklesen PnL: ${total_pnl:.2f}")
    print("=" * 70)

if __name__ == "__main__":
    get_recent_fills()
