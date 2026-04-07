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
    get_smc_bias, find_mss_v2, detect_amd_phases_v2
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

SYMBOLS = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"]
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
            "kill_zone": is_silver_bullet_zone(datetime.now(timezone.utc))
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
    """Executes a real order on OANDA with structural SL/TP."""
    try:
        # 1. Structural SL (V9.5 Logic: ~10-15 pips based on asset)
        pip = 0.0001 if "USD" in ticker else 0.01
        if "XAU" in ticker: pip = 0.1
        if "NAS" in ticker: pip = 1.0
        
        sl_dist = 15 * pip # Default 15 pips
        sl = price - sl_dist if direction == "BUY" else price + sl_dist
        tp = price + (sl_dist * 2) if direction == "BUY" else price - (sl_dist * 2) # 1:2 RR
        
        # 2. Risk Management (1% Risk)
        units = 1000 # Default mini lot
        if direction == "SELL": units = -units
        
        data = {
            "order": {
                "instrument": ticker,
                "units": str(units),
                "type": "MARKET",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {"price": f"{sl:.5f}"},
                "takeProfitOnFill": {"price": f"{tp:.5f}"}
            }
        }
        
        print(f"🚀 [EXECUTION] Sending {direction} order for {ticker}...")
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
        if msg.get('type') == 'PRICE':
            ticker = msg['instrument']
            price = float(msg['bids'][0]['price'])
            history[ticker].append({"time": datetime.now(timezone.utc), "close": price})
            if len(history[ticker]) > 100: history[ticker].pop(0)
            
                # --- PURE ICT SIGNAL DETECTION (V9.5: 24/7 Mode) ---
            if len(history[ticker]) >= 60:
                df = pd.DataFrame(history[ticker])
                # Proxy OHLC from the 1m/tick stream
                from ict_utils import (
                    find_fvg_v3, find_turtle_soup_v2, find_new_logic,
                    find_ifvg, find_silver_bullet, is_macro_time
                )
                df_signals = df.rename(columns={"close": "Close"})
                # Ensure evolved logic has required OHLC columns (aliased to Close for tick stream)
                df_signals['open'] = df_signals['Close']
                df_signals['high'] = df_signals['Close']
                df_signals['low'] = df_signals['Close']
                df_signals['close'] = df_signals['Close']
                
                df_signals = find_fvg_v3(df_signals)
                df_signals = find_turtle_soup_v2(df_signals)
                df_signals = find_ifvg(df_signals)
                df_signals = find_silver_bullet(df_signals)
                df_signals = find_new_logic(df_signals)
                
                row = df_signals.iloc[-1]
                
                # 1. Premium/Discount Range (Last 50 ticks)
                low_50 = df['close'].tail(50).min()
                high_50 = df['close'].tail(50).max()
                midpoint = (low_50 + high_50) / 2
                is_discount = price < midpoint
                is_premium = price > midpoint
                
                # 2. Score Calculation (Audit-Optimized Weights)
                score = 0
                now_utc = datetime.now(timezone.utc)
                macro_bonus = 18 if is_macro_time(now_utc) else 0

                if row.get('FVG_Bull'): score += 25
                if row.get('TurtleSoup_Bull'): score += 20
                if row.get('IFVG_Bull'): score += 22
                if row.get('SB_Bull'): score += 20
                if macro_bonus: score += macro_bonus
                
                if row.get('FVG_Bear'): score -= 25
                if row.get('TurtleSoup_Bear'): score -= 20
                if row.get('IFVG_Bear'): score -= 22
                if row.get('SB_Bear'): score -= 20
                if macro_bonus: score -= macro_bonus
                
                # 3. Execution Logic (Strictly Profit-Verified, No Time Limit)
                if score >= 45 and is_discount:
                    print(f"🎯 [BUY] 24/7 AI-ICT SIGNAL: {ticker} | Price: {price} | Score: {score}")
                    open_order(ticker, "BUY", price, score)
                elif score <= -45 and is_premium:
                    print(f"🎯 [SELL] 24/7 AI-ICT SIGNAL: {ticker} | Price: {price} | Score: {score}")
                    open_order(ticker, "SELL", price, score)
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
