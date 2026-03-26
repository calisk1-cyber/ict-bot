import json
import os
from datetime import datetime

KNOWLEDGE_FILE = "ict_knowledge_base.json"

def save_market_snapshot(symbol, data):
    """
    Belirli bir andaki piyasa durumunu ogrenme icin kaydeder.
    data: Indicators, Regime, Score, News, HTF Bias
    """
    if not os.path.exists(KNOWLEDGE_FILE):
        with open(KNOWLEDGE_FILE, 'w') as f:
            json.dump({}, f)

    with open(KNOWLEDGE_FILE, 'r') as f:
        kb = json.load(f)

    if symbol not in kb:
        kb[symbol] = []

    snapshot = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "metrics": data
    }
    
    kb[symbol].append(snapshot)
    
    # Sadece son 1000 ogrenme verisini tut (Hafiza yonetimi)
    if len(kb[symbol]) > 1000:
        kb[symbol] = kb[symbol][-1000:]

    with open(KNOWLEDGE_FILE, 'w') as f:
        json.dump(kb, f, indent=4)

def get_symbol_track_record(symbol):
    """Gecmis performans verilerini analiz icin dondurur."""
    if not os.path.exists(KNOWLEDGE_FILE): return []
    with open(KNOWLEDGE_FILE, 'r') as f:
        kb = json.load(f)
    return kb.get(symbol, [])
