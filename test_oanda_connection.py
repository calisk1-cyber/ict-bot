import os
from dotenv import load_dotenv
from oandapyV20 import API
import oandapyV20.endpoints.accounts as accounts
import oandapyV20.endpoints.trades as trades

load_dotenv()

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")

print(f"Testing OANDA Connection...")
print(f"Env: {OANDA_ENV}")
print(f"Account: {OANDA_ACCOUNT_ID}")

client = API(access_token=OANDA_API_KEY, environment=OANDA_ENV)

try:
    r = accounts.AccountSummary(OANDA_ACCOUNT_ID)
    client.request(r)
    print("SUCCESS! Account Summary retrieved.")
    print(r.response)
except Exception as e:
    print(f"FAILED! Error: {e}")

try:
    r = trades.TradesList(OANDA_ACCOUNT_ID)
    client.request(r)
    print("SUCCESS! Trades List retrieved.")
except Exception as e:
    print(f"FAILED (Trades)! Error: {e}")
