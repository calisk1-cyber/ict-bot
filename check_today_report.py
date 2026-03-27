import sqlite3
from datetime import datetime

def check_today():
    try:
        conn = sqlite3.connect('ict_bot.db')
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        print(f"Checking trades for: {today}")
        
        # Use date() function on timestamp column
        c.execute("SELECT * FROM trades WHERE date(timestamp) = ?", (today,))
        trades = c.fetchall()
        
        if not trades:
            print("Today: No trades found.")
        else:
            print(f"Today: Found {len(trades)} trades.")
            for t in trades:
                # Column mapping based on database_manager.py:
                # 0: id, 1: timestamp, 2: ticker, 3: direction, 11: pnl (corrected index)
                # Let's just print key info
                print(f"ID: {t[0]} | Time: {t[1]} | Ticker: {t[2]} | Dir: {t[3]} | PnL: {t[11]} | Status: {t[9]}")
        
        # Also check general stats
        c.execute("SELECT COUNT(pnl), SUM(pnl), COUNT(CASE WHEN pnl > 0 THEN 1 END) FROM trades WHERE status='CLOSED'")
        res = c.fetchone()
        if res and res[0] > 0:
             total, net_pnl, wins = res
             wr = (wins / total * 100) if total > 0 else 0
             print(f"\n--- Global Summary ---")
             print(f"Total Trades: {total} | Win Rate: {wr:.1f}% | Net PnL: {net_pnl:.2f}")
             
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_today()
