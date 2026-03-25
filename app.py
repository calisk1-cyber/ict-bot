import os
import json
import time
import pytz
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from openai import OpenAI
from oandapyV20 import API
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.instruments as instruments
from ict_utils import (
    is_silver_bullet_zone, is_macro_time, find_fvg_v3, 
    find_ifvg, find_turtle_soup, find_inducement
)
from news_utils import is_news_volatile

# --- 1. CONFIGURATION & ENV ---
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"), override=True)

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# High-Liquidity Symbols for Scaling
SYMBOLS = [
    "EUR_USD", "GBP_USD", "XAU_USD", "NAS100_USD", 
    "US30_USD", "GBP_JPY", "USD_JPY"
]

client = OpenAI(api_key=OPENAI_API_KEY)
oanda_api = API(access_token=OANDA_API_KEY, environment=OANDA_ENV)
NEWS_TRADING_MODE = True

# --- 2. OANDA EXECUTION ENGINE ---
def get_oanda_bars(symbol, granularity='M5', count=100):
    try:
        params = {"count": count, "granularity": granularity}
        r = instruments.InstrumentsCandles(instrument=symbol, params=params)
        oanda_api.request(r)
        data = []
        for c in r.response.get('candles', []):
            if c['complete']:
                data.append({
                    'time': c['time'],
                    'Open': float(c['mid']['o']),
                    'High': float(c['mid']['h']),
                    'Low': float(c['mid']['l']),
                    'Close': float(c['mid']['c']),
                    'Volume': int(c['volume'])
                })
        df = pd.DataFrame(data)
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
        return df
    except Exception as e:
        print(f"OANDA Data Error ({symbol}): {e}")
        return pd.DataFrame()

def execute_market_order(symbol, units, direction, sl=None, tp=None):
    try:
        order_units = str(units) if direction == "LONG" else str(-units)
        data = {
            "order": {
                "units": order_units,
                "instrument": symbol,
                "timeInForce": "FOK",
                "type": "MARKET",
                "positionFill": "DEFAULT"
            }
        }
        if sl: data["order"]["stopLossOnFill"] = {"price": f"{sl:.5f}"}
        if tp: data["order"]["takeProfitOnFill"] = {"price": f"{tp:.5f}"}
        
        r = orders.OrderCreate(OANDA_ACCOUNT_ID, data=data)
        oanda_api.request(r)
        print(f"✅ ORDER EXECUTED: {symbol} {direction} @ {units} units")
        return r.response
    except Exception as e:
        print(f"❌ ORDER FAILED: {e}")
        return None

# --- 3. AI EXPERT GATEKEEPER ---
def openai_expert_approve(signal, news_context=None):
    """Confirm signal using advanced ICT knowledge base."""
    try:
        news_str = f"HABER UYARISI: {news_context}" if news_context else "Haber yok (Güvenli)."
        prompt = f"""
        ICT EXPERT ANALYSIS REQUEST:
        Ticker: {signal['ticker']} | Direction: {signal['direction']}
        Confidence Score: {signal['score']}/100
        Confluence Reasons: {', '.join(signal['reasons'])}
        {news_str}
        
        Mandatory Check:
        1. Is there a clear Liquidity Sweep before this move?
        2. Is the timing within a Silver Bullet or Macro window?
        3. Is there Displacement (FVG)?
        
        Respond ONLY in JSON format: {{"decision": "APPROVE" | "REJECT", "reasoning": "short explanation"}}
        """
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are the world's best ICT Smar Money Concept analyst trained by Michael J. Huddleston methodology."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        res = json.loads(response.choices[0].message.content)
        return res['decision'] == "APPROVE"
    except:
        return False

# --- 4. TRADING ROUTINE ---
def trading_routine(ticker):
    try:
        now_utc = datetime.now(pytz.UTC)
        is_volatile, news_title = is_news_volatile(ticker)
        
        # HABER ANINDA OZEL MOD (News Hunt)
        if is_volatile and NEWS_TRADING_MODE:
            print(f"🔥 HABER MODU AKTIF [{ticker}]: {news_title}. 1M Grafikte Judas Swing Araniyor...")
            # Haber aninda 1 dakikalik hizli veri çek
            df = get_oanda_bars(ticker, granularity='M1', count=30)
            if df.empty: return
            
            df = find_turtle_soup(df, lookback=15)
            df = find_fvg_v3(df)
            last = df.iloc[-1]
            
            # JUDAS SWING: Sert igne (Sweep) + Hemen ardindan FVG
            if last['TurtleSoup_Bull'] and last['FVG_Bull']:
                print(f"🎯 JUDAS SWING YAKALANDI (Bullish News Reversal)!")
                price = last['Close']
                execute_market_order(ticker, 2000, "LONG", sl=price-0.0030, tp=price+0.0090) # Haber volatilitesi için genis SL/TP
                return
            elif last['TurtleSoup_Bear'] and last['FVG_Bear']:
                print(f"🎯 JUDAS SWING YAKALANDI (Bearish News Reversal)!")
                price = last['Close']
                execute_market_order(ticker, 2000, "SHORT", sl=price+0.0030, tp=price-0.0090)
                return
            return # Haber aninda sadece Judas Swing kovala, normal scora bakma

        # NORMAL MOD (Haber yoksa)
        if is_volatile and not NEWS_TRADING_MODE:
            print(f"🛑 HABER KORUMASI: Islem yapilmiyor.")
            return

        # 1. Normal M5 Analizi
        df = get_oanda_bars(ticker, granularity='M5', count=100)
        if df.empty: return
        
        df = find_turtle_soup(df)
        df = find_fvg_v3(df)
        df = find_ifvg(df)
        df = find_inducement(df)
        
        last = df.iloc[-1]
        score = 0
        reasons = []
        
        # Scoring Confluences
        if is_silver_bullet_zone(now_utc): score += 30; reasons.append("Silver Bullet Window")
        elif is_macro_time(now_utc): score += 20; reasons.append("Macro Time Window")
        
        if last['TurtleSoup_Bull']: score += 25; reasons.append("Liquidity Sweep (Bull)")
        elif last['TurtleSoup_Bear']: score -= 25; reasons.append("Liquidity Sweep (Bear)")
        
        if last['FVG_Bull']: score += 20; reasons.append("FVG Positive Displacement")
        elif last['FVG_Bear']: score -= 20; reasons.append("FVG Negative Displacement")
        
        if last.get('IFVG_Bull'): score += 15; reasons.append("Inversion FVG Confirmed")
        
        # Decision Logic
        direction = "HOLD"
        if score >= 70: direction = "LONG"
        elif score <= -70: direction = "SHORT"
        
        if direction != "HOLD":
            signal = {"ticker": ticker, "direction": direction, "score": score, "reasons": reasons}
            if openai_expert_approve(signal):
                # Execution with Risk Management (1:3 RR)
                price = last['Close']
                dist = 0.0015 # 15 pips baseline
                sl = price - dist if direction == "LONG" else price + dist
                tp = price + (dist * 3.0) if direction == "LONG" else price - (dist * 3.0)
                execute_market_order(ticker, 1000, direction, sl=sl, tp=tp)
                
    except Exception as e:
        print(f"Error in {ticker} routine: {e}")

def main():
    print("🚀 ICT EXPERT BOT V3 - STARTING MULTI-SYMBOL ENGINE...")
    print(f"Watching: {', '.join(SYMBOLS)}")
    with ThreadPoolExecutor(max_workers=5) as executor:
        while True:
            executor.map(trading_routine, SYMBOLS)
            time.sleep(300) # 5m Cycle

if __name__ == "__main__":
    main()
