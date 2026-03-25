import json
import csv
import os
from datetime import datetime

LOG_FILE = "ict_trade_history.csv"

def log_ict_attempt(data):
    """
    Sinyal denemelerini ve sonuçlarını loglar.
    Data keys: ticker, direction, score, reasons, regime, er, status, price
    """
    file_exists = os.path.isfile(LOG_FILE)
    
    with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'timestamp', 'ticker', 'direction', 'score', 
            'reasons', 'regime', 'efficiency_ratio', 'status', 'price'
        ])
        
        if not file_exists:
            writer.writeheader()
            
        row = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'ticker': data.get('ticker'),
            'direction': data.get('direction'),
            'score': data.get('score'),
            'reasons': "|".join(data.get('reasons', [])),
            'regime': data.get('regime'),
            'efficiency_ratio': f"{data.get('er', 0):.4f}",
            'status': data.get('status'),
            'price': f"{data.get('price', 0):.5f}"
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
