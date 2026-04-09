import sqlite3
from datetime import datetime, timedelta

def check_recent():
    try:
        conn = sqlite3.connect('ict_bot.db')
        c = conn.cursor()
        
        # Get overall stats
        c.execute("SELECT COUNT(*), SUM(pnl), SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) FROM trades WHERE status='CLOSED'")
        total, total_pnl, wins = c.fetchone()
        
        print(f"--- Genel İstatistikler ---")
        print(f"Toplam İşlem: {total}")
        print(f"Toplam Kâr/Zarar: {total_pnl if total_pnl else 0:.2f}")
        print(f"Başarı Oranı: {(wins/total*100) if total else 0:.1f}%")
        
        # Get last 5 trades
        print(f"\n--- Son 5 İşlem ---")
        c.execute("SELECT timestamp, ticker, direction, pnl, status FROM trades ORDER BY timestamp DESC LIMIT 5")
        for row in c.fetchall():
            print(f"Zaman: {row[0]} | Parite: {row[1]} | Yön: {row[2]} | PnL: {row[3]} | Durum: {row[4]}")
            
        conn.close()
    except Exception as e:
        print(f"Veritabanı hatası: {e}")

if __name__ == '__main__':
    check_recent()
