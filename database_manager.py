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
    conn.commit()
    conn.close()
    print("--- SQLITE DATABASE READY ---")

def log_trade(data):
    """Inserts a new trade into the trades table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO trades (ticker, direction, signal_type, score, entry_price, sl, tp, status, units, ai_decision, red_flags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('ticker'), data.get('direction'), data.get('signal_type'), 
        data.get('score'), data.get('entry_price'), data.get('sl'), 
        data.get('tp'), data.get('status', 'OPEN'), data.get('units', 0),
        data.get('ai_decision'), data.get('red_flags')
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

if __name__ == "__main__":
    init_database()
