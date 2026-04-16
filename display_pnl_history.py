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
    
    # Fetch last 500 closed trades for better statistics
    params = {"state": "CLOSED", "count": 500}
    try:
        r = trades.TradesList(accountID=account_id, params=params)
        client.request(r)
        all_trades = r.response.get('trades', [])
        
        if not all_trades:
            print("No closed trades found.")
            return

        # Prepare for daily grouping
        daily_stats = {}
        total_pnl = 0.0
        total_wins = 0
        total_trades = 0

        for t in all_trades:
            pnl = float(t.get('realizedPL', 0.0))
            time_str = t.get('closeTime', 'N/A')
            date_str = time_str[:10] # YYYY-MM-DD
            symbol = t.get('instrument', 'N/A')
            
            if date_str not in daily_stats:
                daily_stats[date_str] = {'pnl': 0.0, 'wins': 0, 'count': 0}
            
            daily_stats[date_str]['pnl'] += pnl
            daily_stats[date_str]['count'] += 1
            if pnl > 0: daily_stats[date_str]['wins'] += 1
            
            total_pnl += pnl
            total_trades += 1
            if pnl > 0: total_wins += 1

        # PRINT DAILY SUMMARY
        print(f"\n{'='*75}")
        print(f"   OANDA DAILY PERFORMANCE SUMMARY")
        print(f"{'='*75}")
        header = f"{'Date':<15} | {'PnL ($)':<12} | {'Trades':<8} | {'Win Rate (%)':<15}"
        print(header)
        print("-" * len(header))
        
        # Sort by date (descending)
        for d in sorted(daily_stats.keys(), reverse=True):
            s = daily_stats[d]
            wr = (s['wins'] / s['count']) * 100
            print(f"{d:<15} | {s['pnl']:>+11.2f} | {s['count']:<8} | {wr:>12.1f}%")
            
        print("-" * len(header))
        overall_wr = (total_wins / total_trades) * 100 if total_trades > 0 else 0
        print(f"{'TOTALS':<15} | {total_pnl:>+11.2f} | {total_trades:<8} | {overall_wr:>12.1f}%")
        print(f"{'='*75}\n")
        
        # PRO-TIP
        print("Note: To see individual trade details, use 'export_oanda_history.py'.")

    except Exception as e:
        print(f"Error fetching history: {e}")
        
    except Exception as e:
        print(f"Error fetching history: {e}")

if __name__ == "__main__":
    display_full_pnl_history()
