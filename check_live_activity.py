import os
import oandapyV20
import oandapyV20.endpoints.trades as trades
import oandapyV20.endpoints.orders as orders
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

def check_live_status():
    access_token = os.getenv("OANDA_API_KEY")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    client = oandapyV20.API(access_token=access_token, environment=os.getenv("OANDA_ENV", "practice"))
    
    print(f"--- [LIVE MONITOR] Checking Account: {account_id} ---")
    
    # 1. Open Trades
    r_trades = trades.TradesList(accountID=account_id)
    client.request(r_trades)
    open_trades = r_trades.response.get('trades', [])
    
    print(f"\n[ACTIVE POSITIONS]: {len(open_trades)}")
    for t in open_trades:
        print(f"  --> {t['instrument']} {t['currentUnits']} @ {t['price']} (Unrealized PnL: {t['unrealizedPL']})")
    
    # 2. Recent Transactions (Today)
    from oandapyV20.endpoints.transactions import TransactionList
    r_trans = TransactionList(accountID=account_id)
    # We just want the latest ones
    client.request(r_trans)
    last_id = r_trans.response.get('lastTransactionID')
    
    print(f"\nLast Transaction ID: {last_id}")
    print("------------------------------------------")

if __name__ == "__main__":
    check_live_status()
