import os
from oandapyV20 import API
import oandapyV20.endpoints.accounts as accounts
from dotenv import load_dotenv

load_dotenv()

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")

client = API(access_token=OANDA_API_KEY, environment=OANDA_ENV)
r = accounts.AccountSummary(OANDA_ACCOUNT_ID)
client.request(r)
summary = r.response.get('account', {})
print(f"Account Balance: {summary.get('balance')}")
print(f"Currency: {summary.get('currency')}")
