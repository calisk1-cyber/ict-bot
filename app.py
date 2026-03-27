import os
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
    try:
        import subprocess
        print(f"--- RUNNING BACKTEST FOR {ticker} ---")
        # Run and wait for completion
        result = subprocess.run(["py", "realistic_backtest_v8.py"], capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            return jsonify({"status": "ERROR", "message": f"Script failed: {result.stderr[:200]}"})
            
        if os.path.exists("backtest_experiments.json"):
            with open("backtest_experiments.json", "r") as f:
                exps = json.load(f)
                if exps:
                    return jsonify(exps[-1])
        
        return jsonify({"status": "ERROR", "message": "No results in experiments file"})
    except Exception as e:
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
