import os
import json
import asyncio
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from oandapyV20 import API
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.pricing as pricing
from oandapyV20.endpoints import accounts
from ict_utils import (
    is_in_algorithmic_window_v18, apply_ict_v18_omniscient, 
    calculate_ote_v15
)
from database_manager import log_trade

# --- SETUP ---
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"), override=True)

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")

api = API(access_token=OANDA_API_KEY, environment=OANDA_ENV)
SYMBOLS = ["USD_JPY", "XAU_USD", "USD_CAD"]

def open_v18_order(ticker, direction, price):
    """V18 Sovereign Execution Engine"""
    try:
        # 1. Live Balance Sync
        r_acc = accounts.AccountSummary(OANDA_ACCOUNT_ID)
        api.request(r_acc)
        balance = float(r_acc.response.get('account', {}).get('balance', 100000.0))
        risk_amount = balance * 0.01 
        
        # 2. Structural Precision
        pip = 0.0001 if "USD" in ticker else 0.01
        if "XAU" in ticker: pip = 0.1
        sl_dist = 12 * pip
        
        sl = price - sl_dist if direction == "BUY" else price + sl_dist
        tp = price + (sl_dist * 1.8) if direction == "BUY" else price - (sl_dist * 1.8)
        units = int(risk_amount / sl_dist)
        if direction == "SELL": units = -units
        
        data = {
            "order": {
                "instrument": ticker, "units": str(units), "type": "MARKET",
                "stopLossOnFill": {"price": f"{sl:.5f}"},
                "takeProfitOnFill": {"price": f"{tp:.5f}"}
            }
        }
        
        print(f"🚀 [BOT 4 EXECUTION] {ticker} {direction} {units} units (Risk: ${risk_amount:.2f})")
        r = orders.OrderCreate(OANDA_ACCOUNT_ID, data=data)
        api.request(r)
        
        # 3. Log
        log_trade({
            "ticker": ticker, "direction": direction, "entry_price": price,
            "sl": sl, "tp": tp, "units": units, "score": 99,
            "signal_type": "V18 SOVEREIGNTY", "status": "OPEN"
        })
        return True
    except Exception as e:
        print(f"❌ [BOT 4 ERROR] {e}")
        return False

async def main_loop():
    print("==================================================")
    print(" SINGULARITY V18 SOVEREIGNTY - BOT 4 ACTIVE ")
    print(f" Portfolyo: {SYMBOLS} | Risk: 1%")
    print("==================================================")
    
    r = pricing.PricingStream(accountID=OANDA_ACCOUNT_ID, params={"instruments": ",".join(SYMBOLS)})
    history = {s: [] for s in SYMBOLS}
    
    def _gen(): return api.request(r)

    for msg in _gen():
        # 1. Time Check
        now = datetime.now(timezone.utc)
        if not is_in_algorithmic_window_v18(now):
            continue

        if msg.get('type') == 'PRICE':
            ticker = msg['instrument']
            price = float(msg['bids'][0]['price'])
            history[ticker].append({"time": now, "close": price})
            if len(history[ticker]) > 100: history[ticker].pop(0)
            
            # 2. V18 Logic
            if len(history[ticker]) >= 60:
                df = pd.DataFrame(history[ticker]).rename(columns={"close": "Close"})
                df_v18 = apply_ict_v18_omniscient(df)
                row = df_v18.iloc[-1]
                
                if row.get('is_algo_window'):
                    if row.get('CISD_Bull'):
                        open_v18_order(ticker, "BUY", price)
                    elif row.get('CISD_Bear'):
                        open_v18_order(ticker, "SELL", price)
                        
        await asyncio.sleep(0.01)

if __name__ == "__main__":
    asyncio.run(main_loop())
