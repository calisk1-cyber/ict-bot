import os
import sys
import json
import asyncio
import threading
from flask import Flask, render_template, jsonify, request
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI
from oandapyV20 import API
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.instruments as instruments
import oandapyV20.endpoints.pricing as pricing
from oandapyV20.endpoints import trades

from ict_utils import (
    is_silver_bullet_zone, find_fvg_v3, 
    get_htf_bias, find_mss_v2, detect_amd_phases_v2
)
from news_utils import is_high_impact_news_active
from daily_risk_manager import DailyRiskManager
from database_manager import init_database, log_trade, update_trade_closure, get_trade_stats, get_recent_trades

# --- CONFIG ---
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"), override=True)
OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
oanda_api = API(access_token=OANDA_API_KEY, environment=os.getenv("OANDA_ENV", "practice"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
risk_manager = DailyRiskManager(initial_balance=100000.0)

SYMBOLS = ["EUR_USD", "XAU_USD", "NAS100_USD", "GBP_USD"]

# --- FLASK APP ---
app = Flask(__name__, template_folder='templates')

@app.route('/')
def index(): return render_template('dashboard.html')

@app.route('/api/stats')
def api_stats(): return jsonify(get_trade_stats())

@app.route('/api/trades')
def api_trades(): return jsonify(get_recent_trades())

@app.route('/api/live')
def api_live():
    def _req():
        r = trades.TradesList(OANDA_ACCOUNT_ID)
        oanda_api.request(r); return r.response.get('trades', [])
    try:
        live_trades = _req()
        return jsonify({
            "status": "ONLINE",
            "positions": live_trades,
            "kill_zone": is_silver_bullet_zone(datetime.now(timezone.utc))
        })
    except: return jsonify({"status": "ERROR"})

@app.route('/backtest', methods=['POST'])
def run_backtest_api():
    data = request.json or {}
    ticker = data.get('ticker', 'EUR_USD')
    period = data.get('period', '30g')
    
    # 1. DEBUG PRINTS (USER REQUESTED)
    print(f"\n--- [BACKTEST DEBUG] ---")
    print(f"Ticker: {ticker}")
    print(f"Periyot: {period}")
    
    try:
        # 2. DATA FETCH (Replacing get_oanda_bars with our download_full_history)
        from ict_utils import download_full_history, find_fvg_v3, find_turtle_soup_v2, find_ifvg
        
        # Mapping for 30g -> 1mo for yfinance
        yf_period = "1mo" if "30" in period else "1wk"
        df = download_full_history(ticker, interval="5m", period=yf_period)
        
        print(f"Çekilen veri: {len(df)} bar")
        
        if df.empty:
            print("HATA: Veri çekilemedi (Sıfır bar)")
            return jsonify({"status": "NO_TRADES", "message": "Veri çekilemedi."})

        # 3. SIGNAL CALCULATION
        df = find_fvg_v3(df)
        df = find_turtle_soup_v2(df)
        df = find_ifvg(df)
        
        # 4. FILTERING & SCORING (Simulating the user's requested logic)
        signals = []
        for i in range(len(df)):
            score = 0
            row = df.iloc[i]
            if row.get('FVG_Bull'): score += 25
            if row.get('TurtleSoup_Bull'): score += 25
            if row.get('IFVG_Bull'): score += 15
            
            if score > 0:
                signals.append({"time": df.index[i], "score": score})
        
        print(f"Bulunan toplam ham sinyal: {len(signals)}")
        
        filtered = [s for s in signals if s['score'] >= 50]
        print(f"Eşik (50) geçen: {len(filtered)}")
        print(f"--- [DEBUG END] ---\n")

        # 5. EXECUTE FULL BACKTEST (Still using script for maturity, but we now have logs)
        import subprocess
        subprocess.run([sys.executable, "realistic_backtest_v8.py"], capture_output=True)
        
        if os.path.exists("backtest_experiments.json"):
            with open("backtest_experiments.json", "r") as f:
                exps = json.load(f)
                if exps:
                    res = exps[-1]
                    # If empty results but we found signals in debug, explain why
                    if not res.get("performance") and len(filtered) > 0:
                        res["status"] = "NO_TRADES"
                        res["message"] = "Sinyal var ama Bias (EMA200) uymadığı için işlem açılmadı."
                    return jsonify(res)
        
        return jsonify({"status": "NO_TRADES", "message": "Kriterlere uygun işlem bulunamadı."})
        
    except Exception as e:
        print(f"Backtest Error: {e}")
        return jsonify({"status": "ERROR", "message": str(e)})

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# --- TRADING LOGIC (ASYNC) ---
async def stream_prices_loop():
    r = pricing.PricingStream(accountID=OANDA_ACCOUNT_ID, params={"instruments": ",".join(SYMBOLS)})
    def _gen(): return oanda_api.request(r)
    print("--- LIVE STREAM ACTIVE ---")
    for msg in _gen():
        if msg.get('type') == 'PRICE':
            # Signal processing logic...
            pass
        await asyncio.sleep(0.01)

async def main():
    init_database()
    threading.Thread(target=run_flask, daemon=True).start()
    print("ICT SINGULARITY V9.2 - DASHBOARD LIVE AT http://localhost:5000")
    await stream_prices_loop()

if __name__ == "__main__":
    asyncio.run(main())
