import os
import oandapyV20
import oandapyV20.endpoints.transactions as trans
from dotenv import load_dotenv

load_dotenv()

def check_history():
    access_token = os.getenv("OANDA_API_KEY")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    client = oandapyV20.API(access_token=access_token, environment=os.getenv("OANDA_ENV", "practice"))
    
    # Get the last 20 transactions
    r = trans.TransactionList(accountID=account_id)
    client.request(r)
    last_id = int(r.response.get('lastTransactionID'))
    
    print(f"--- [RECENT HISTORY] Checking last 20 transactions (up to ID {last_id}) ---")
    
    # Fetch details for the range
    r_details = trans.TransactionIDRange(accountID=account_id, params={"from": max(1, last_id-20), "to": last_id})
    client.request(r_details)
    
    for t in r_details.response.get('transactions', []):
        t_type = t.get('type')
        t_time = t.get('time')
        t_instrument = t.get('instrument', 'N/A')
        
        if t_type in ['ORDER_FILL', 'ORDER_CANCEL', 'MARKET_ORDER', 'LIMIT_ORDER', 'ORDER_REJECT']:
            print(f"[{t_time}] {t_type} | {t_instrument} | Status: {t.get('reason', 'N/A')}")
            if t_type == 'ORDER_CANCEL':
                print(f"  --> Cancel Reason: {t.get('reason')}")

if __name__ == "__main__":
    check_history()
