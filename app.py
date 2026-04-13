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
from oandapyV20.endpoints import trades, accounts

from ict_utils import (
    is_in_algorithmic_window_v18, apply_ict_v18_omniscient, 
    calculate_ote_v15
)
from news_utils import is_high_impact_news_active
from daily_risk_manager import DailyRiskManager
from database_manager import init_database, log_trade, update_trade_closure, get_trade_stats, get_recent_trades
from db_models import Strategy, BacktestResult, LiveTrade, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# --- OANDA CONFIG ---
base_dir = os.path.dirname(os.path.abspath(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(base_dir, ".env"), override=True)

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")

# Use consistent variable name and environment
oanda_api = API(access_token=OANDA_API_KEY, environment=OANDA_ENV)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
risk_manager = DailyRiskManager(initial_balance=100000.0)

# --- BOT DATABASE SETUP ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///ict_bot.db")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

SYMBOLS = ["USD_JPY", "XAU_USD", "USD_CAD"]
# oanda_api = API(access_token=OANDA_ACCESS_TOKEN, environment="practice" if "practice" in OANDA_ACCOUNT_ID else "live") # REMOVED: BROKEN

# --- FLASK APP ---
app = Flask(__name__, template_folder='templates')

@app.route('/')
def index(): return render_template('matrix.html')

@app.route('/api/stats')
@app.route('/api/status')
def api_stats(): return jsonify(get_trade_stats())

@app.route('/api/trades')
def api_trades(): return jsonify(get_recent_trades())

@app.route('/api/live')
@app.route('/api/portfolio')
def api_live():
    def _req():
        r = trades.TradesList(OANDA_ACCOUNT_ID)
        oanda_api.request(r); return r.response.get('trades', [])
    try:
        live_trades = _req()
        return jsonify({
            "status": "ONLINE",
            "positions": live_trades,
            "kill_zone": is_in_algorithmic_window_v18(datetime.now(timezone.utc))
        })
    except: return jsonify({"status": "ERROR"})

@app.route('/api/bot_statuses')
def get_bot_statuses():
    print("API: Fetching bot statuses...")
    try:
        from base_agent import BaseAgent
        temp_agent = BaseAgent("StatusFetcher")
        if temp_agent.redis_client:
            statuses = temp_agent.redis_client.hgetall("bot_statuses")
            # Parse JSON strings back to dicts
            result = {name: json.loads(val) for name, val in statuses.items()}
            return jsonify(result)
        return jsonify({})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/backtest_reports')
def get_backtest_reports():
    """Returns the latest backtest results joined with strategy names."""
    try:
        session = Session()
        from sqlalchemy import desc
        results = session.query(BacktestResult, Strategy.name)\
            .join(Strategy, BacktestResult.strategy_id == Strategy.id)\
            .order_by(desc(BacktestResult.backtested_at))\
            .limit(50)\
            .all()
        
        report_list = []
        for res, name in results:
            report_list.append({
                "id": res.id,
                "strategy_id": res.strategy_id,
                "name": name,
                "total_return": res.total_return,
                "win_rate": res.win_rate,
                "max_drawdown": res.max_drawdown,
                "sharpe": res.sharpe_ratio,
                "passed": res.passed,
                "date": res.backtested_at.strftime("%H:%M:%S")
            })
        session.close()
        return jsonify(report_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/toggle_bot', methods=['POST'])
def toggle_bot():
    # Placeholder for toggling logic
    return jsonify({"status": "SUCCESS", "message": "Bot toggle initiated"})

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
                        res["message"] = "Sinyal var ama SMC Bias uymadığı için işlem açılmadı."
                    return jsonify(res)
        
        return jsonify({"status": "NO_TRADES", "message": "Kriterlere uygun işlem bulunamadı."})
        
    except Exception as e:
        print(f"Backtest Error: {e}")
        return jsonify({"status": "ERROR", "message": str(e)})

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def open_order(ticker, direction, price, score):
    """Executes a real order on OANDA with dynamic 1% risk sizing."""
    try:
        # 1. Fetch Account Balance for Risk Calculation
        r_acc = accounts.AccountSummary(OANDA_ACCOUNT_ID)
        oanda_api.request(r_acc)
        balance = float(r_acc.response.get('account', {}).get('balance', 100000.0))
        risk_amount = balance * 0.01 # 1% Risk
        
        # 2. Structural SL
        pip = 0.0001 if "USD" in ticker else 0.01
        if "XAU" in ticker: pip = 0.1
        
        sl_dist = 25 * pip # Scalp yerine Intraday bazli (25 pips)
        sl = price - sl_dist if direction == "BUY" else price + sl_dist
        tp = price + (sl_dist * 2.5) if direction == "BUY" else price - (sl_dist * 2.5) # R/R 1:2.5
        
        # --- INSTITUTIONAL UNIT HAKKEDİŞ (FIXED) ---
        if "XAU" in ticker:
            units = int(risk_amount / sl_dist)
        elif "JPY" in ticker:
            # USD/JPY: Units = Risk / (Dist / Entry)
            units = int(risk_amount / (sl_dist / price))
        else:
            # EUR_USD etc: Units = Risk / Dist
            units = int(risk_amount / sl_dist)
            
        if direction == "SELL": units = -units
        
        # Precision handling (JPY pairs use 3 decimals, others 5)
        precision = 3 if "JPY" in ticker else 5

        data = {
            "order": {
                "instrument": ticker,
                "units": str(units),
                "type": "MARKET",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {"price": f"{sl:.{precision}f}"},
                "takeProfitOnFill": {"price": f"{tp:.{precision}f}"}
            }
        }
        
        print(f"🚀 [V18 EXECUTION] {direction} {units} units on {ticker} (Risk: ${risk_amount:.2f})")
        r = orders.OrderCreate(OANDA_ACCOUNT_ID, data=data)
        oanda_api.request(r)
        
        # 3. Log to Database
        log_trade({
            "ticker": ticker,
            "direction": direction,
            "entry_price": price,
            "sl": sl,
            "tp": tp,
            "units": units,
            "score": score,
            "signal_type": "AI-ICT SIGNAL",
            "status": "OPEN",
            "ai_decision": "APPROVED",
            "red_flags": "NONE"
        })
        return True
    except Exception as e:
        print(f"❌ [ORDER ERROR] {e}")
        return False

# --- TRADING LOGIC (ASYNC) ---
async def stream_prices_loop():
    r = pricing.PricingStream(accountID=OANDA_ACCOUNT_ID, params={"instruments": ",".join(SYMBOLS)})
    def _gen(): return oanda_api.request(r)
    print("--- LIVE STREAM ACTIVE ---")
    
    # Store recent prices for signal calculation
    history = {s: [] for s in SYMBOLS}
    
    for msg in _gen():
        # Efficiency Check: Only process if in Algorithmic Window
        if not is_in_algorithmic_window_v18(datetime.now(timezone.utc)):
            continue

        if msg.get('type') == 'PRICE':
            ticker = msg['instrument']
            
            # --- HIGH IMPACT NEWS FILTER (DISABLED FOR 100% BACKTEST PARITY) ---
            # if is_high_impact_news_active(ticker):
            #     print(f"⚠️ [NEWS PROTECT] Skipping {ticker} due to high impact news.")
            #     continue

            price = float(msg['bids'][0]['price'])
            history[ticker].append({"time": datetime.now(timezone.utc), "close": price})
            if len(history[ticker]) > 100: history[ticker].pop(0)
            
            # --- V18 OMNISCIENT SIGNAL DETECTION ---
            if len(history[ticker]) >= 60:
                df = pd.DataFrame(history[ticker])
                # ... signal math ...
                df_v18 = apply_ict_v18_omniscient(df)
                row = df_v18.iloc[-1]
                
                if row.get('is_algo_window'):
                    is_bull = row.get('CISD_Bull')
                    is_bear = row.get('CISD_Bear')
                    
                    if is_bull:
                        print(f"🎯 [V18 BUY] OMNISCIENT SIGNAL: {ticker} @ {price}")
                        open_order(ticker, "BUY", price, 99)
                    elif is_bear:
                        print(f"🎯 [V18 SELL] OMNISCIENT SIGNAL: {ticker} @ {price}")
                        open_order(ticker, "SELL", price, 99)
        await asyncio.sleep(0.01)

# In streamer loop, before calling signals, add:
# df_signals['open'] = df_signals['Close']
# df_signals['high'] = df_signals['Close']
# df_signals['low'] = df_signals['Close']


async def main():
    init_database()
    threading.Thread(target=run_flask, daemon=True).start()
    print("ICT SINGULARITY V9.2 - DASHBOARD LIVE AT http://localhost:5000")
    await stream_prices_loop()

if __name__ == "__main__":
    asyncio.run(main())
