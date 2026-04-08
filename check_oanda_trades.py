import os
import json
from v20 import Context
from dotenv import load_dotenv

load_dotenv()

def check_recent_trades():
    token = os.getenv("OANDA_API_KEY")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    env = os.getenv("OANDA_ENV", "practice")
    
    ctx = Context(
        "api-fxpractice.oanda.com" if env == "practice" else "api-fxtrade.oanda.com",
        443,
        True,
        application="CheckTrades",
        token=token
    )
    
    try:
        # Get last 20 transactions
        response = ctx.transaction.get_range(account_id, fromID=1) # Simplified or use transactions since
        # Actually better use account summary and recent trades
        response = ctx.trade.list(account_id, state="ALL", count=10)
        trades = response.get("trades", 200)
        
        print(f"--- SON 10 İŞLEM (OANDA) ---")
        if not trades:
            print("Bugün veya yakın zamanda hiç işlem bulunamadı.")
        for t in trades:
            print(f"ID: {t.id} | {t.instrument} | {t.currentUnits} | Status: {t.state} | PnL: {t.realizedPL} | Open: {t.openTime}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_recent_trades()
