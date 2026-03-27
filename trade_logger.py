import json
import csv
import os
from datetime import datetime

LOG_FILE = "ict_trade_history.csv"

def log_ict_attempt(data):
    """
    Sinyal denemelerini ve sonuçlarını loglar.
    Data keys: ticker, direction, score, reasons, regime, er, status, price, sl, tp, pnl, ai_decision, red_flags
    """
    file_exists = os.path.isfile(LOG_FILE)
    
    with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'timestamp', 'ticker', 'direction', 'signal_type', 'score', 
            'entry_price', 'sl', 'tp', 'status', 'pnl', 'ai_decision', 'red_flags'
        ])
        
        if not file_exists:
            writer.writeheader()
            
        row = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'ticker': data.get('ticker'),
            'direction': data.get('direction'),
            'signal_type': "|".join(data.get('reasons', []))[:50],
            'score': data.get('score'),
            'entry_price': f"{data.get('price', 0):.5f}",
            'sl': f"{data.get('sl', 0):.5f}",
            'tp': f"{data.get('tp', 0):.5f}",
            'status': data.get('status'),
            'pnl': f"{data.get('pnl', 0):.2f}",
            'ai_decision': data.get('ai_decision', 'PENDING'),
            'red_flags': data.get('red_flags', 'NONE')
        }
        writer.writerow(row)

def get_last_trades(n=10):
    """Son işlemleri analiz için çeker."""
    if not os.path.exists(LOG_FILE): return []
    try:
        with open(LOG_FILE, mode='r', encoding='utf-8') as f:
            lines = f.readlines()
            return lines[-n:]
    except:
        return []
