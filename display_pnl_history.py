import os
import oandapyV20
import oandapyV20.endpoints.trades as trades
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime

load_dotenv()

def display_full_pnl_history():
    access_token = os.getenv("OANDA_API_KEY")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    env = os.getenv("OANDA_ENV", "practice")
    
    if not access_token or not account_id:
        print("Error: OANDA credentials missing in .env")
        return
        
    client = oandapyV20.API(access_token=access_token, environment=env)
    
    print(f"\n{'='*70}")
    print(f"   OANDA TRADE HISTORY (CLOSED POSITIONS)")
    print(f"{'='*70}")
    
    # Fetch last 100 closed trades
    params = {"state": "CLOSED", "count": 100}
    try:
        r = trades.TradesList(accountID=account_id, params=params)
        client.request(r)
        all_trades = r.response.get('trades', [])
        
        if not all_trades:
            print("No closed trades found.")
            return

        header = f"{'Close Time':<25} | {'Symbol':<10} | {'Units':<8} | {'PnL ($)':<10}"
        print(header)
        print("-" * len(header))
        
        total_pnl = 0.0
        # Oanda returns trades from newest to oldest by default usually, if not we reverse
        for t in reversed(all_trades):
            pnl = float(t.get('realizedPL', 0.0))
            time_str = t.get('closeTime', 'N/A')[:19].replace('T', ' ')
            symbol = t.get('instrument', 'N/A')
            units = float(t.get('initialUnits', 0.0))
            
            pnl_str = f"{pnl:+.2f}"
            print(f"{time_str:<25} | {symbol:<10} | {abs(units):<8} | {pnl_str:<10}")
            total_pnl += pnl
            
        print("-" * len(header))
        print(f"{'TOTAL PROFIT/LOSS':<47} | {total_pnl:+.2f}")
        print(f"{'='*70}\n")
        
    except Exception as e:
        print(f"Error fetching history: {e}")

if __name__ == "__main__":
    display_full_pnl_history()
