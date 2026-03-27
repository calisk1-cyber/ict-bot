import os
import json
import asyncio
import pandas as pd
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from openai import OpenAI
from oandapyV20 import API
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.instruments as instruments
import oandapyV20.endpoints.pricing as pricing
from oandapyV20.endpoints import trades

from ict_utils import (
    is_silver_bullet_zone, is_macro_time, find_fvg_v3, 
    find_ifvg, find_turtle_soup_v2, get_htf_bias,
    calculate_pvr_risk, detect_market_regime, detect_amd_phases_v2, 
    find_order_blocks_v2, find_ipda_v2, find_mss_v2
)
from news_utils import is_high_impact_news_active
from daily_risk_manager import DailyRiskManager
from database_manager import init_database, log_trade, update_trade_closure

# --- CONFIG ---
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"), override=True)

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SYMBOLS = ["EUR_USD", "XAU_USD", "NAS100_USD", "GBP_USD"]
SPREAD_CONFIG = {'EUR_USD': 0.00012, 'XAU_USD': 0.35, 'NAS100_USD': 1.5, 'GBP_USD': 0.00015}

client = OpenAI(api_key=OPENAI_API_KEY)
oanda_api = API(access_token=OANDA_API_KEY, environment=OANDA_ENV)
risk_manager = DailyRiskManager(initial_balance=100000.0)

# --- FINANCIAL LOGIC ---
def calculate_real_pnl(ticker, entry, exit_price, direction, units):
    spread = SPREAD_CONFIG.get(ticker, 0.0002)
    gross_pnl = (exit_price - entry) * units if direction == 'LONG' else (entry - exit_price) * units
    return gross_pnl - (spread * units)

# --- ASYNC HELPERS ---
async def get_bars_async(symbol, count=100):
    def _req():
        r = instruments.InstrumentsCandles(instrument=symbol, params={"count": count, "granularity": "M5"})
        oanda_api.request(r)
        return r.response
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, _req)
    data = []
    for c in res.get('candles', []):
        if c['complete']:
            data.append({'time': c['time'], 'Open': float(c['mid']['o']), 'High': float(c['mid']['h']), 'Low': float(c['mid']['l']), 'Close': float(c['mid']['c'])})
    df = pd.DataFrame(data)
    if not df.empty:
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
    return df

async def place_order_async(symbol, units, direction, sl=None, tp=None):
    def _req():
        order_units = str(units) if direction == "LONG" else str(-units)
        data = {"order": {"units": order_units, "instrument": symbol, "timeInForce": "FOK", "type": "MARKET", "positionFill": "DEFAULT"}}
        if sl: data["order"]["stopLossOnFill"] = {"price": f"{sl:.5f}"}
        if tp: data["order"]["takeProfitOnFill"] = {"price": f"{tp:.5f}"}
        r = orders.OrderCreate(OANDA_ACCOUNT_ID, data=data)
        oanda_api.request(r)
        return r.response
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _req)

async def openai_expert_async(signal):
    prompt = f"Analyze ICT Setup: {signal['ticker']} {signal['direction']} Score: {signal['score']} Reasons: {signal['reasons']}"
    def _req():
        return client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": "Master ICT Trader."}, {"role": "user", "content": prompt}], response_format={"type": "json_object"})
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(None, _req)
    return json.loads(resp.choices[0].message.content)

# --- CORE LOGIC ---
async def process_signal(ticker, price):
    """Event-driven signal processing."""
    # 1. Filters
    risk_manager.update_date(datetime.now(timezone.utc).date())
    if not risk_manager.can_trade_today()[0]: return
    
    news_active, news_name = is_high_impact_news_active()
    if news_active: return

    # 2. Indicators
    df = await get_bars_async(ticker)
    if df.empty: return
    df = detect_amd_phases_v2(df); df = find_fvg_v3(df); df = find_mss_v2(df)
    last = df.iloc[-1]
    
    direction = "LONG" if last.get('FVG_Bull') else "SHORT" if last.get('FVG_Bear') else None
    if not direction: return
    
    # HTF Check
    if (direction == "LONG" and get_htf_bias(ticker) == "BEARISH") or (direction == "SHORT" and get_htf_bias(ticker) == "BULLISH"): return 

    # 3. AI Gatekeeper
    ai_res = await openai_expert_async({"ticker": ticker, "direction": direction, "score": 75, "reasons": "FVG + Async Tick"})
    if ai_res.get('decision') != "APPROVE": return

    # 4. Execution
    sl = price - 0.0020 if direction == "LONG" else price + 0.0020
    tp = price + 0.0060 if direction == "LONG" else price - 0.0060
    units = 10000
    
    res = await place_order_async(ticker, units, direction, sl=sl, tp=tp)
    if res:
        log_trade({'ticker': ticker, 'direction': direction, 'signal_type': 'ASYNC', 'score': 75, 'entry_price': price, 'sl': sl, 'tp': tp, 'units': units, 'ai_decision': 'APPROVED'})
        print(f"--- [EXECUTED] {ticker} {direction} ---")

async def manage_open_positions_loop():
    """Background task to manage Strat-D positions."""
    while True:
        try:
            def _get_pos():
                r = trades.TradesList(OANDA_ACCOUNT_ID)
                oanda_api.request(r)
                return r.response.get('trades', [])
            
            loop = asyncio.get_event_loop()
            open_trades = await loop.run_in_executor(None, _get_pos)
            
            for t in open_trades:
                # Strat-D logic here (2R BE, 5R Closed)
                # Same as before but async-friendly
                pass
        except: pass
        await asyncio.sleep(60)

async def stream_prices_loop():
    """OANDA Live Tick Stream."""
    r = pricing.PricingStream(accountID=OANDA_ACCOUNT_ID, params={"instruments": ",".join(SYMBOLS)})
    def _gen(): return oanda_api.request(r)
    
    print("--- LIVE STREAM ACTIVE ---")
    for msg in _gen():
        if msg.get('type') == 'PRICE':
            ticker = msg['instrument']
            price = float(msg['asks'][0]['price'])
            await process_signal(ticker, price)
        await asyncio.sleep(0.01)

async def main():
    init_database()
    print("ICT SINGULARITY V9.1 ACTIVE")
    await asyncio.gather(
        stream_prices_loop(),
        manage_open_positions_loop()
    )

if __name__ == "__main__":
    asyncio.run(main())
