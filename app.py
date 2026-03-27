import os
import json
import time
import pytz
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from openai import OpenAI
from oandapyV20 import API
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.instruments as instruments
import oandapyV20.endpoints.accounts as accounts
from oandapyV20.endpoints import trades
from ict_utils import (
    is_silver_bullet_zone, is_macro_time, find_fvg_v3, 
    find_ifvg, find_turtle_soup_v2, detect_market_regime,
    get_htf_bias, save_chart_image, find_smt_divergence_v2, find_mss_v2,
    calculate_pvr_risk, detect_amd_phases_v2, find_order_blocks_v2,
    find_ipda_v2, find_liquidity_sweep_v2, find_breaker_blocks
)
from news_utils import is_news_volatile
from trade_logger import log_ict_attempt
from knowledge_manager import save_market_snapshot
from daily_risk_manager import DailyRiskManager

# --- 1. CONFIGURATION ---
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"), override=True)

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SYMBOLS = ["EUR_USD", "GBP_USD", "XAU_USD", "NAS100_USD", "US30_USD", "GBP_JPY", "USD_JPY"]

client = OpenAI(api_key=OPENAI_API_KEY)
oanda_api = API(access_token=OANDA_API_KEY, environment=OANDA_ENV)
risk_manager = DailyRiskManager(initial_balance=100000.0) 

# Dynamic Weights
WEIGHTS_FILE = "optimized_weights.json"
STRATEGY_WEIGHTS = {"silver_bullet": 25, "macro": 20, "turtle_soup": 25, "fvg": 20, "ifvg": 20, "smt": 30, "mss": 25, "ob": 15}

def load_optimized_weights():
    global STRATEGY_WEIGHTS
    if os.path.exists(WEIGHTS_FILE):
        try:
            with open(WEIGHTS_FILE, 'r') as f:
                STRATEGY_WEIGHTS.update(json.load(f))
        except: pass

load_optimized_weights()

# --- KB LEARNING (NEW REQ 5) ---
KB_FILE = "ict_knowledge_base.json"
def learn_from_success(ticker, direction, setup_type, rr, time_reached):
    try:
        if os.path.exists(KB_FILE):
            with open(KB_FILE, 'r') as f:
                kb = json.load(f)
        else:
            kb = {"successful_setups": []}
            
        kb["successful_setups"].append({
            "ticker": ticker,
            "direction": direction,
            "setup": setup_type,
            "rr_reached": rr,
            "timestamp": time_reached,
            "learned_at": datetime.now().isoformat()
        })
        
        with open(KB_FILE, 'w') as f:
            json.dump(kb, f, indent=4)
        print(f"--- LEARNED NEW SETUP: {setup_type} on {ticker} ---")
    except Exception as e:
        print(f"FAILED TO LEARN: {e}")

# --- 2. OANDA CORE ENGINE (NO EMOJIS) ---
def safe_request(func, retries=3):
    for i in range(retries):
        try:
            return func()
        except Exception as e:
            print(f"ERROR {i+1}/{retries}: {e}")
            time.sleep(2 * (i+1))
    return None

def get_oanda_bars(symbol, granularity='M5', count=100):
    def _req():
        r = instruments.InstrumentsCandles(instrument=symbol, params={"count": count, "granularity": granularity})
        oanda_api.request(r)
        data = []
        for c in r.response.get('candles', []):
            if c['complete']:
                data.append({'time': c['time'], 'Open': float(c['mid']['o']), 'High': float(c['mid']['h']), 'Low': float(c['mid']['l']), 'Close': float(c['mid']['c']), 'Volume': int(c['volume'])})
        df = pd.DataFrame(data)
        if not df.empty:
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
        return df
    return safe_request(_req)

def place_oanda_order(symbol, units, direction, sl=None, tp=None):
    def _req():
        order_units = str(units) if direction == "LONG" else str(-units)
        data = {"order": {"units": order_units, "instrument": symbol, "timeInForce": "FOK", "type": "MARKET", "positionFill": "DEFAULT"}}
        if sl: data["order"]["stopLossOnFill"] = {"price": f"{sl:.5f}"}
        if tp: data["order"]["takeProfitOnFill"] = {"price": f"{tp:.5f}"}
        r = orders.OrderCreate(OANDA_ACCOUNT_ID, data=data)
        oanda_api.request(r)
        return r.response
    return safe_request(_req)

def get_oanda_positions():
    def _req():
        r = trades.TradesList(OANDA_ACCOUNT_ID)
        oanda_api.request(r)
        return r.response.get('trades', [])
    return safe_request(_req)

def close_partial_oanda(trade_id, units):
    def _req():
        data = {"units": str(int(units))}
        r = trades.TradeClose(accountID=OANDA_ACCOUNT_ID, tradeID=trade_id, data=data)
        oanda_api.request(r)
        return r.response
    return safe_request(_req)

def move_sl_to_breakeven(trade_id, entry_price):
    def _req():
        data = {"stopLoss": {"price": str(round(entry_price, 5))}}
        r = trades.TradeOrdersReplace(accountID=OANDA_ACCOUNT_ID, tradeID=trade_id, data=data)
        oanda_api.request(r)
        return r.response
    return safe_request(_req)

def check_oanda_connection():
    def _req():
        r = accounts.AccountSummary(OANDA_ACCOUNT_ID)
        oanda_api.request(r)
        return r.response
    return safe_request(_req) is not None

def get_vix():
    # Placeholder: Returns a stable value if no actual VIX data is available
    return 18.5

# --- 3. STRATEGY D: POSITION MGMT ---
def manage_open_positions():
    open_trades = get_oanda_positions()
    if not open_trades: return
    
    for t in open_trades:
        try:
            tid = t['id']
            symbol = t['instrument']
            entry = float(t['price'])
            curr_units = abs(float(t['currentUnits']))
            is_long = float(t['currentUnits']) > 0
            
            sl_order = t.get('stopLossOrder', {})
            if not sl_order: continue
            sl_price = float(sl_order.get('price', 0))
            if sl_price == 0: continue
            
            risk = abs(entry - sl_price)
            if risk == 0: continue
            
            df = get_oanda_bars(symbol, count=1)
            if df is None or df.empty: continue
            cp = df['Close'].iloc[-1]
            pnl_r = (cp - entry) / risk if is_long else (entry - cp) / risk
            
            # 2R Milestone
            if pnl_r >= 2.0 and curr_units > 1000:
                print(f"2R REACHED [{symbol}]: Partial Closing 50% & SL to BE")
                close_partial_oanda(tid, curr_units * 0.5)
                move_sl_to_breakeven(tid, entry)
                learn_from_success(symbol, "LONG" if is_long else "SHORT", "Strategy D Partial", 2, datetime.now().isoformat())
            
            # 5R Milestone
            elif pnl_r >= 5.0:
                print(f"5R REACHED [{symbol}]: Closing Full Position")
                close_partial_oanda(tid, curr_units)
                learn_from_success(symbol, "LONG" if is_long else "SHORT", "Strategy D Full", 5, datetime.now().isoformat())
        except Exception as e:
            print(f"Manage Position Error: {e}")

# ---  ICT V2 SIGNALS ---
def get_full_ict_signal(ticker):
    df = get_oanda_bars(ticker, count=100)
    if df is None or df.empty: return None
    
    df = detect_amd_phases_v2(df)
    df = find_turtle_soup_v2(df)
    df = find_fvg_v3(df)
    df = find_ifvg(df)
    df = find_order_blocks_v2(df)
    df = find_ipda_v2(df)
    df = find_mss_v2(df)
    
    corr_pair = "GBP_USD" if ticker == "EUR_USD" else "EUR_USD" if ticker == "GBP_USD" else None
    if corr_pair:
        df_corr = get_oanda_bars(corr_pair, count=100)
        if df_corr is not None and not df_corr.empty:
            df = find_smt_divergence_v2(df, df_corr)
            
    last = df.iloc[-1]
    score = 0
    reasons = []
    now_utc = datetime.now(timezone.utc)
    
    if is_silver_bullet_zone(now_utc): score += STRATEGY_WEIGHTS['silver_bullet']; reasons.append("SB")
    if is_macro_time(now_utc): score += STRATEGY_WEIGHTS['macro']; reasons.append("MACRO")
    if last.get('TurtleSoup_Bull'): score += STRATEGY_WEIGHTS['turtle_soup']; reasons.append("TSBULL")
    if last.get('TurtleSoup_Bear'): score -= STRATEGY_WEIGHTS['turtle_soup']; reasons.append("TSBEAR")
    if last.get('FVG_Bull'): score += STRATEGY_WEIGHTS['fvg']; reasons.append("FVGBULL")
    if last.get('FVG_Bear'): score -= STRATEGY_WEIGHTS['fvg']; reasons.append("FVGBEAR")
    
    return {"df": df, "score": score, "reasons": reasons, "price": last['Close']}

# --- AI EXPERT (REFINED PROMPT) ---
def openai_expert_approve(signal):
    try:
        vix = get_vix()
        prompt = f"""
        Analyze this ICT setup. Respond ONLY in JSON: {{"decision": "APPROVE"|"REJECT", "red_flags": "none|list", "reasoning": "..."}}
        Ticker: {signal['ticker']} | Score: {signal['score']} | Reasons: {signal['reasons']}
        Current VIX: {vix}
        
        Mandatory Check: 
        1. AMD Distribution: Is price in the expansion phase?
        2. Daily Limits: Avoid -2% drawdown threshold.
        3. Correlation: Check for excessive exposure in {signal['ticker']}.
        4. VIX Strategy: If VIX > 30, REJECT unless high confidence.
        """
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Master ICT Trader. Analyze AMD Distribution, Daily Limits, Correlation and VIX. Reject if VIX > 30."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        res = json.loads(response.choices[0].message.content)
        return res
    except: return {"decision": "REJECT", "red_flags": "API_ERROR"}

# --- TRADING ROUTINE ---
def trading_routine(ticker):
    risk_manager.update_date(datetime.now(timezone.utc).date())
    can_trade, msg = risk_manager.can_trade_today()
    if not can_trade: return

    volatile, title = is_news_volatile(ticker)
    if volatile: return

    res = get_full_ict_signal(ticker)
    if not res or abs(res['score']) < 70: return
    
    direction = "LONG" if res['score'] > 0 else "SHORT"
    htf = get_htf_bias(ticker)
    if (direction == "LONG" and htf == "BEARISH") or (direction == "SHORT" and htf == "BULLISH"):
        return 
        
    signal_data = {"ticker": ticker, "direction": direction, "score": res['score'], "reasons": res['reasons']}
    ai_res = openai_expert_approve(signal_data)
    
    if ai_res['decision'] == "APPROVE":
        price = res['price']
        dist = 0.0020
        sl = price - dist if direction == "LONG" else price + dist
        tp = price + dist * 3 if direction == "LONG" else price - dist * 3
        
        units = calculate_pvr_risk(res['df'], base_units=10000)
        order = place_oanda_order(ticker, units, direction, sl=sl, tp=tp)
        if order:
            print(f"ORDER EXECUTED: {ticker} {direction}")
            log_ict_attempt({
                'ticker': ticker, 'direction': direction, 'score': res['score'],
                'reasons': res['reasons'], 'price': price, 'sl': sl, 'tp': tp,
                'status': 'EXECUTED', 'ai_decision': 'APPROVED', 'red_flags': ai_res.get('red_flags', 'NONE')
            })
            risk_manager.register_trade_result(-100) # Placeholder
    else:
        log_ict_attempt({
            'ticker': ticker, 'direction': direction, 'score': res['score'],
            'reasons': res['reasons'], 'price': res['price'], 'status': 'AI_REJECTED',
            'ai_decision': 'REJECTED', 'red_flags': ai_res.get('red_flags', 'NONE')
        })

def main():
    print("ICT SINGULARITY ENGINE V2 - LIVE")
    if not check_oanda_connection():
        print("OANDA CONNECTION FAILED. EXITING.")
        return
    print("OANDA CONNECTED.")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        while True:
            manage_open_positions() 
            executor.map(trading_routine, SYMBOLS)
            time.sleep(60) 

if __name__ == "__main__":
    main()
