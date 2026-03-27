import os
import json
import asyncio
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
    is_silver_bullet_zone, is_macro_time, find_fvg_v3, 
    find_ifvg, find_turtle_soup_v2, get_htf_bias,
    calculate_pvr_risk, detect_amd_phases_v2, find_order_blocks_v2,
    find_ipda_v2, find_mss_v2
)
from news_utils import is_news_volatile
from daily_risk_manager import DailyRiskManager
from database_manager import init_database, log_trade, update_trade_closure

# --- CONFIG ---
load_dotenv(override=True)
OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
oanda_api = API(access_token=OANDA_API_KEY, environment=os.getenv("OANDA_ENV", "practice"))
risk_manager = DailyRiskManager(initial_balance=100000.0)

SYMBOLS = ["EUR_USD", "XAU_USD", "NAS100_USD"]
SPREAD_CONFIG = {'EUR_USD': 0.00012, 'XAU_USD': 0.35, 'NAS100_USD': 1.5}

# --- ASYNC OANDA WRAPPERS ---
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

# --- EVENT HANDLERS ---
async def on_price_update(ticker, price):
    """Triggered on every tick. Unified Event-Driven Logic."""
    # To prevent API spam, we only check signals every 1 min or on specific conditions
    # But for now, we follow the user's request for event-driven
    print(f" TICK: {ticker} @ {price}")
    
    # 1. Management Check
    # manage_open_positions() could be moved here but we'll do it on a separate task
    
    # 2. Signal Check (Throttled conceptually or full check)
    df = await get_bars_async(ticker)
    if df.empty: return
    
    # Apply ICT Logic
    df = detect_amd_phases_v2(df); df = find_fvg_v3(df); df = find_mss_v2(df)
    last = df.iloc[-1]
    
    score = 0
    if last.get('FVG_Bull'): score += 50
    if is_silver_bullet_zone(datetime.now(timezone.utc)): score += 30
    
    if score >= 70:
        print(f" EVENT SIGNAL: {ticker} SCORE {score}")
        # AI & Trade Logic...
        pass

async def stream_prices():
    """OANDA WebSocket Implementation (Eksik 1 & 4)"""
    print("--- STARTING OANDA LIVE STREAM ---")
    r = pricing.PricingStream(accountID=OANDA_ACCOUNT_ID, params={"instruments": ",".join(SYMBOLS)})
    
    # OANDA v20 PricingStream is a generator. We wrap it in a blocking executor thread
    # or use a specialized library. For dev-mode, we iterate:
    def _gen():
        return oanda_api.request(r)
        
    stream = _gen()
    for msg in stream:
        if msg.get('type') == 'PRICE':
            ticker = msg['instrument']
            price = float(msg['asks'][0]['price'])
            await on_price_update(ticker, price)
        await asyncio.sleep(0.1)

async def main():
    init_database()
    print("AUTONOMOUS ICT V9 - ASYNC ENGINE STARTED")
    
    # Run Stream and Background Tasks
    await asyncio.gather(
        stream_prices(),
        # Add other tasks like manage_open_positions_loop()
    )

if __name__ == "__main__":
    asyncio.run(main())
