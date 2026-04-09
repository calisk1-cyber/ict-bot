from flask import Flask, render_template, jsonify
import sqlite3
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from oandapyV20 import API
import oandapyV20.endpoints.trades as trades
import oandapyV20.endpoints.transactions as trans

app = Flask(__name__)
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"), override=True)

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")
client = API(access_token=OANDA_API_KEY, environment=OANDA_ENV)

def get_real_oanda_data():
    """Oanda API'sinden tum acik ve bugunku kapali islemleri ceker."""
    all_real = []
    try:
        # 1. ACIK ISLEMLER
        r_open = trades.TradesList(OANDA_ACCOUNT_ID)
        client.request(r_open)
        for t in r_open.response.get('trades', []):
            all_real.append({
                "id": f"o_{t['id']}",
                "timestamp": t['openTime'][:19].replace('T', ' '),
                "ticker": t['instrument'],
                "direction": "BUY" if int(t['currentUnits']) > 0 else "SELL",
                "entry_price": float(t['price']),
                "pnl": float(t['unrealizedPL']),
                "status": "OPEN",
                "ai_reason": "Canlı Pozisyon"
            })
            
        # 2. KAPALI ISLEMLER (Son 50 Transaction)
        r_trans = trans.TransactionList(OANDA_ACCOUNT_ID)
        client.request(r_trans)
        last_id = int(r_trans.response.get('lastTransactionID', 0))
        
        # Son id'den geriye dogru birkac tane bakalim (Pratik cozum)
        r_since = trans.TransactionSinceID(OANDA_ACCOUNT_ID, params={"id": max(1, last_id - 50)})
        client.request(r_since)
        for tx in r_since.response.get('transactions', []):
            if tx['type'] == 'ORDER_FILL':
                # Sadece kapama islemlerini (PnL uretenleri) alalim
                pl = float(tx.get('pl', 0))
                if pl != 0:
                    all_real.append({
                        "id": f"tx_{tx['id']}",
                        "timestamp": tx['time'][:19].replace('T', ' '),
                        "ticker": tx['instrument'],
                        "direction": "BUY" if int(tx.get('units', 0)) > 0 else "SELL",
                        "entry_price": float(tx.get('price', 0)),
                        "pnl": pl,
                        "status": "CLOSED",
                        "ai_reason": "Oanda Geçmişi"
                    })
    except Exception as e:
        print(f"Oanda API Hatasi: {e}")
        
    return all_real

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/trades')
def api_trades():
    oanda_data = get_real_oanda_data()
    
    # Sort and filter today only (optional, filter for clarity)
    today_str = datetime.now().strftime("%Y-%m-%d")
    final_list = [t for t in oanda_data if t['timestamp'].startswith(today_str)]
    
    # If no real data for today, show dummy to avoid empty screen for UI demo
    if not final_list:
        final_list = [{"id": "d1", "timestamp": f"{today_str} 18:10:00", "ticker": "OANDA_YOK", "direction": "BUY", "entry_price": 0, "pnl": 0, "status": "REKLAM", "ai_reason": "Beklemede"}]

    final_list.sort(key=lambda x: x['timestamp'], reverse=True)

    summary = {
        "total_pnl": sum(t.get('pnl', 0) for t in final_list),
        "total_trades": len(final_list),
        "win_rate": round(sum(1 for t in final_list if t.get('pnl', 0) > 0) / len(final_list) * 100, 1) if final_list else 0
    }
    
    return jsonify({"trades": final_list, "summary": summary})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
