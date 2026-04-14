import sqlite3
import os
from datetime import datetime

DB_PATH = "ict_bot.db"

def init_database():
    """Initializes the SQLite database with trades and daily_stats tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Trades Table: Complete lifecycle of a trade
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            ticker TEXT,
            direction TEXT,
            signal_type TEXT,
            score INTEGER,
            entry_price REAL,
            sl REAL,
            tp REAL,
            status TEXT, -- 'OPEN', 'CLOSED', 'AI_REJECTED'
            units INTEGER,
            pnl REAL DEFAULT 0.0,
            ai_decision TEXT,
            ai_reason TEXT,
            red_flags TEXT,
            exit_price REAL,
            exit_time DATETIME
        )
    """)
    
    # Daily Stats Table: Performance tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            total_trades INTEGER,
            win_rate REAL,
            net_pnl REAL,
            max_dd REAL,
            sharpe REAL
        )
    """)
    # --- MIGRATION LOGIC (Add missing columns if table exists) ---
    columns_to_add = [
        ("ai_decision", "TEXT"),
        ("ai_reason", "TEXT"),
        ("red_flags", "TEXT"),
        ("score", "INTEGER"),
        ("exit_price", "REAL"),
        ("exit_time", "DATETIME")
    ]
    
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass # Column already exists
            
    conn.commit()
    conn.close()
    print("--- SQLITE DATABASE READY & MIGRATED ---")

def log_trade(data):
    """Inserts a new trade into the trades table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO trades (ticker, direction, signal_type, score, entry_price, sl, tp, status, units, ai_decision, ai_reason, red_flags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('ticker'), data.get('direction'), data.get('signal_type'), 
        data.get('score'), data.get('entry_price'), data.get('sl'), 
        data.get('tp'), data.get('status', 'OPEN'), data.get('units', 0),
        data.get('ai_decision', 'APPROVED'), data.get('ai_reason'), data.get('red_flags')
    ))
    trade_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trade_id

def update_trade_closure(trade_id, exit_price, pnl):
    """Updates a trade when it is closed."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE trades 
        SET exit_price = ?, pnl = ?, status = 'CLOSED', exit_time = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (exit_price, pnl, trade_id))
    conn.commit()
    conn.close()

def get_recent_trades(limit=20):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_trade_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # PnL & Win Rate
    cursor.execute("SELECT COUNT(pnl), SUM(pnl), COUNT(CASE WHEN pnl > 0 THEN 1 END) FROM trades WHERE status='CLOSED'")
    total, net_pnl, wins = cursor.fetchone()
    total = total or 0; net_pnl = net_pnl or 0; wins = wins or 0
    wr = (wins / total * 100) if total > 0 else 0
    
    # Live Positions
    cursor.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'")
    live_pos = cursor.fetchone()[0]
    
    conn.close()
    return {
        "total_pnl": float(net_pnl), "win_rate": float(wr), "total_trades": int(total),
        "max_dd": 0.0, "sharpe": 0.0, "live_pos": int(live_pos)
    }

if __name__ == "__main__":
    init_database()
