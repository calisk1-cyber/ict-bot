import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def check_oanda_actual():
    token = os.getenv("OANDA_API_KEY")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    env = os.getenv("OANDA_ENV", "practice")
    
    host = "api-fxpractice.oanda.com" if env == "practice" else "api-fxtrade.oanda.com"
    url = f"https://{host}/v3/accounts/{account_id}/trades"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            trades = response.json().get("trades", [])
            print(f"--- AKTİF İŞLEMLER ({len(trades)}) ---")
            for t in trades:
                print(f"ID: {t['id']} | {t['instrument']} | {t['currentUnits']} | State: {t['state']} | PnL: {t['unrealizedPL']}")
            
            # Check closed trades
            url_closed = f"https://{host}/v3/accounts/{account_id}/transactions?count=10"
            res_c = requests.get(url_closed, headers=headers)
            if res_c.status_code == 200:
                pages = res_c.json().get("pages", [])
                print(f"\n--- SON 10 İŞLEM BİLGİSİ ---")
                if not pages:
                    print("Yeni işlem kaydı bulunamadı.")
                else:
                    last_page = pages[-1]
                    res_p = requests.get(last_page, headers=headers)
                    for trans in res_p.json().get("transactions", []):
                        if "tradeID" in trans or "orderID" in trans:
                            print(f"Type: {trans['type']} | Time: {trans['time']} | ID: {trans.get('id')}")
        else:
            print(f"API Hatası: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_oanda_actual()
