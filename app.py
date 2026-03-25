import os
import json
import csv
import time
import threading
import concurrent.futures
import pytz
from datetime import datetime, time as dt_time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import yfinance as yf
import pandas as pd
import pandas_ta as ta

# OANDA API
import oandapyV20
import oandapyV20.endpoints.instruments as instruments
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.positions as positions
import oandapyV20.endpoints.trades as trades
from oandapyV20.contrib.requests import MarketOrderRequest, TakeProfitDetails, StopLossDetails

from ict_utils import is_kill_zone, detect_amd_phases_v2, find_turtle_soup_v2, find_order_blocks_v2

# HELPER: OANDA instrument naming is different from yfinance

def is_valid_session(timestamp):
    return "NY" if 13 <= timestamp.hour <= 16 else "LONDRA"

base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"), override=True)

app = Flask(__name__, static_folder=base_dir)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize OANDA Client
OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV", "practice")

try:
    oanda_api = oandapyV20.API(access_token=OANDA_API_KEY, environment=OANDA_ENV)
    print("OANDA API Baglantisi Basarili!")
except Exception as e:
    oanda_api = None
    print("OANDA API Baglanti Hatasi:", e)

bot_active = True

WATCHLIST = {
    'EUR_USD':    {'type': 'forex',     'smt_pair': 'GBP_USD',     'lot': 1000},
    'XAU_USD':    {'type': 'commodity', 'smt_pair': 'XAG_USD',     'lot': 1},
    'NAS100_USD': {'type': 'index',     'smt_pair': 'SPX500_USD',  'lot': 1},
    'GBP_USD':    {'type': 'forex',     'smt_pair': 'EUR_USD',     'lot': 1000}
}
bot_status_cache = {ticker: {'signal': 'BEKLEYOR', 'trades': 0, 'pnl': 0} for ticker in WATCHLIST}
scan_logs = [] # Rolling buffer for UI

class RiskCoordinator:
    def __init__(self):
        self.daily_pnl = 0
        self.daily_trades = 0
        self.last_reset = datetime.now(pytz.UTC).date()
    
    def can_trade(self, ticker):
        now_date = datetime.now(pytz.UTC).date()
        if now_date > self.last_reset:
            self.reset_daily()
            
        if self.daily_pnl <= -500: # Örnek: $500 max gunluk kayip
            return False, "Günlük kayıp limitine ulaşıldı"
        
        if self.daily_trades >= 10:
            return False, "Günlük işlem limiti doldu"
            
        return True, "Onaylandı"

    def reset_daily(self):
        self.daily_pnl = 0
        self.daily_trades = 0
        self.last_reset = datetime.now(pytz.UTC).date()
        print("🔄 Günlük limitler sıfırlandı")

risk_coord = RiskCoordinator()

# === OANDA HELPERS ===

def get_oanda_bars(instrument, granularity='M5', count=100):
    if not oanda_api: return pd.DataFrame()
    try:
        params = {"count": count, "granularity": granularity}
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        oanda_api.request(r)
        
        data = []
        for candle in r.response.get('candles', []):
            if not candle['complete']: continue
            data.append({
                'Time': candle['time'],
                'Open': float(candle['mid']['o']),
                'High': float(candle['mid']['h']),
                'Low': float(candle['mid']['l']),
                'Close': float(candle['mid']['c']),
                'Volume': int(candle['volume'])
            })
        df = pd.DataFrame(data)
        if df.empty: return df
        df.set_index(pd.to_datetime(df['Time']), inplace=True)
        return df
    except Exception as e:
        print(f"OANDA Data Error [{instrument}]: {e}")
        return pd.DataFrame()

def place_oanda_order(instrument, units, side, sl_price, tp_price):
    if not oanda_api: return None
    try:
        # Side check
        units = abs(units) if side == 'LONG' else -abs(units)
        
        order_body = {
            "order": {
                "units": str(units),
                "instrument": instrument,
                "type": "MARKET",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {"price": str(round(sl_price, 5))},
                "takeProfitOnFill": {"price": str(round(tp_price, 5))}
            }
        }
        r = orders.OrderCreate(OANDA_ACCOUNT_ID, data=order_body)
        oanda_api.request(r)
        print(f"✅ {side} İşlem Açıldı: {instrument} ({units} units)")
        return r.response
    except Exception as e:
        print(f"OANDA Order Error [{instrument}]: {e}")
        return None

def manage_open_positions():
    if not oanda_api: return
    try:
        r = positions.OpenPositions(OANDA_ACCOUNT_ID)
        oanda_api.request(r)
        open_pos = r.response.get('positions', [])
        
        for pos in open_pos:
            instr = pos['instrument']
            manage_trades_strategy_d(instr)
            
    except Exception as e:
        print(f"Monitor error: {e}")

def manage_trades_strategy_d(instrument):
    try:
        r = trades.TradesList(OANDA_ACCOUNT_ID)
        oanda_api.request(r)
        all_trades = r.response.get('trades', [])
        
        for t in all_trades:
            if t['instrument'] != instrument: continue
            
            trade_id = t['id']
            curr_units = int(t['currentUnits'])
            entry_price = float(t['price'])
            side = 'LONG' if curr_units > 0 else 'SHORT'
            
            # Fetch current price
            df = get_oanda_bars(instrument, count=1)
            if df.empty: continue
            curr_price = df.iloc[-1]['Close']
            
            # SL/TP calculation
            sl_price = float(t.get('stopLossOrder', {}).get('price', 0))
            if sl_price == 0: continue
            
            risk = abs(entry_price - sl_price)
            if risk == 0: continue
            
            # Partial Close at 2R
            is_partial = abs(int(t['currentUnits'])) < abs(int(t['initialUnits']))
            
            # Check 2R
            pnl_r = (curr_price - entry_price) / risk if side == 'LONG' else (entry_price - curr_price) / risk
            
            if pnl_r >= 2.0 and not is_partial:
                # Close 50%
                close_units = abs(int(curr_units * 0.5))
                close_body = {"units": str(close_units)}
                r_close = trades.TradeClose(OANDA_ACCOUNT_ID, tradeID=trade_id, data=close_body)
                oanda_api.request(r_close)
                
                # Move SL to BE
                sl_body = {"order": {"timeInForce": "GTC", "price": str(entry_price), "type": "STOP_LOSS", "tradeID": trade_id}}
                r_sl = trades.TradeCRCDO(OANDA_ACCOUNT_ID, tradeID=trade_id, data=sl_body)
                oanda_api.request(r_sl)
                print(f"[PARTIAL] {instrument} 2R: %50 Kapatildi + SL BE Cekildi")
                
    except Exception as e:
        pass

def get_full_ict_signal(ticker, config):
    try:
        # 1. Fetch MTF Data from OANDA
        df_h1 = get_oanda_bars(ticker, granularity='H1', count=200)
        df_m15 = get_oanda_bars(ticker, granularity='M15', count=200)
        df_m5 = get_oanda_bars(ticker, granularity='M5', count=200)
        
        if df_m5.empty or df_m15.empty or df_h1.empty:
            return None
            
        # 2. Indicators & Bias
        df_h1['EMA_200'] = ta.ema(df_h1['Close'], length=200)
        last_h1 = df_h1.iloc[-1]
        ema_val = last_h1.get('EMA_200')
        bias = "BULLISH" if (ema_val is not None and not pd.isna(ema_val) and last_h1['Close'] > ema_val) else "BEARISH"
        
        # 3. V2 Signal Logic (on M5)
        amd_res = detect_amd_phases_v2(df_m5.tail(100))
        ts_res = find_turtle_soup_v2(df_m5.tail(60), lookback=20)
        ob_res = find_order_blocks_v2(df_m5.tail(50))
        
        score = 0
        reasons = []
        direction = "HOLD"
        
        if amd_res:
            if bias == "BULLISH" and amd_res['direction'] == 'LONG': score += 40; reasons.append("AMD LONG")
            elif bias == "BEARISH" and amd_res['direction'] == 'SHORT': score += 40; reasons.append("AMD SHORT")
            
        if ts_res:
            ts_last = ts_res[-1]
            if bias == "BULLISH" and ts_last['direction'] == 'LONG': score += 50; reasons.append("TurtleSoup LONG")
            elif bias == "BEARISH" and ts_last['direction'] == 'SHORT': score += 50; reasons.append("TurtleSoup SHORT")
            
        if score >= 50:
            direction = "LONG" if bias == "BULLISH" else "SHORT"
            
        # ATR for SL/TP
        df_m5['ATR'] = ta.atr(df_m5['High'], df_m5['Low'], df_m5['Close'], length=14)
        atr_val = float(df_m5['ATR'].iloc[-1])
        
        price = float(df_m5['Close'].iloc[-1])
        sl = price - (atr_val * 1.5) if direction == 'LONG' else price + (atr_val * 1.5)
        tp = price + (atr_val * 5.0) if direction == 'LONG' else price - (atr_val * 5.0) # 5R Target
        
        return {
            'ticker': ticker,
            'direction': direction,
            'score': score,
            'entry': price,
            'sl': sl,
            'tp': tp,
            'reasons': reasons,
            'atr': atr_val
        }
    except Exception as e:
        print(f"Signal Error [{ticker}]: {e}")
        return None

def openai_approve(signal):
    if not client: return True # Fallback
    try:
        ticker = signal['ticker']
        prompt = f"ICT Analizi: {ticker} için {signal['direction']} yönünde skor {signal['score']}. Nedenler: {signal['reasons']}. Onaylıyor musun?"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Sen bir ICT uzmanısın. JSON formatında {'decision': 'ONAYLA' | 'RED', 'reasoning': '...'} döndür."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )
        res = json.loads(response.choices[0].message.content)
        print(f"[AI] {ticker} Kararı: {res.get('decision')} | Neden: {res.get('reasoning')}")
        return res.get('decision') == 'ONAYLA'
    except Exception as e:
        print(f"[AI ERROR]: {e}")
        return False

def log_trade(ticker, signal, status, pnl=None):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(base_dir, 'trades_log.csv')
    row = {
        'tarih': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'ticker': ticker,
        'yon': signal.get('direction', ''),
        'sinyal': ", ".join(signal.get('reasons', [])),
        'skor': signal.get('score', 0),
        'giris': signal.get('entry', 0),
        'sl': signal.get('sl', 0),
        'durum': status,
        'pnl': pnl or ''
    }
    file_exists = os.path.exists(log_file)
    with open(log_file, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    
    prefix = '[TRADE]' if status == 'ACILDI' else '[AI_RED]' if status == 'AI_RED' else '[LOG]'
    print(f"{prefix} {row['tarih']} | {ticker} | {status} | Skor:{signal.get('score',0)}")

def daily_summary():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_file = os.path.join(base_dir, 'trades_log.csv')
        if not os.path.exists(log_file): return
        df = pd.read_csv(log_file)
        bugun = datetime.now().strftime('%Y-%m-%d')
        bugun_df = df[df['tarih'].str.startswith(bugun)]
        
        acilan = len(bugun_df[bugun_df['durum'] == 'ACILDI'])
        reddedilen = len(bugun_df[bugun_df['durum'] == 'AI_RED'])
        
        print(f"""
╔══════════════════════════════╗
║      GÜNLÜK ÖZET RAPORU      ║
╠══════════════════════════════╣
║ Tarih    : {bugun}      ║
║ Açılan   : {acilan} işlem            ║
║ AI Red   : {reddedilen} sinyal          ║
╚══════════════════════════════╝
        """)
    except Exception as e:
        print(f"Rapor hatası: {e}")

def run_forever():
    print("[BOT] ICT OANDA Bot baslatildi...")
    while True:
        try:
            now = datetime.now(pytz.UTC)
            in_kill_zone = is_kill_zone(now)
            
            # Kill Zone logic
            if in_kill_zone:
                print(f"[KILLZONE] Aktif ({in_kill_zone}): {now.strftime('%H:%M UTC')}")
                
                def scan_work(ticker, config):
                    sig_res = get_full_ict_signal(ticker, config)
                    
                    # Update cache for UI
                    if ticker not in bot_status_cache: bot_status_cache[ticker] = {'signal': 'BEKLEYOR', 'trades': 0, 'pnl': 0}
                    sig_text = sig_res['direction'] if sig_res else 'HOLD'
                    bot_status_cache[ticker]['signal'] = sig_text
                    
                    score = sig_res.get('score', 0) if sig_res else 0
                    print(f"[SCAN] {ticker}: {sig_text} (Score: {score})")
                    
                    # Log for UI
                    scan_logs.append({
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "ticker": ticker,
                        "msg": f"{sig_text} (Skor: {score})"
                    })
                    if len(scan_logs) > 50: scan_logs.pop(0)
                    
                    if sig_res is not None and int(sig_res.get('score', 0)) >= 50:
                        signal = sig_res # type: dict
                        can_trade, reason = risk_coord.can_trade(ticker)
                        if can_trade:
                            print(f"[AI_WAIT] {ticker} {signal['direction']} onay bekleniyor...")
                            approved = openai_approve(signal)
                            if approved:
                                print(f"[AI_GO] {ticker} onay alindi, emir gonderiliyor...")
                                res = place_oanda_order(ticker, config['lot'], signal['direction'], signal['sl'], signal['tp'])
                                if res: 
                                    print(f"[SUCCESS] {ticker} OANDA emri onaylandi, log yaziliyor...")
                                    log_trade(ticker, signal, 'ACILDI')
                                    risk_coord.daily_trades += 1
                                    bot_status_cache[ticker]['trades'] += 1
                                else:
                                    print(f"[FAIL] {ticker} OANDA emri basarisiz oldu.")
                            else:
                                print(f"[REJECT] {ticker} AI tarafindan reddedildi.")
                                log_trade(ticker, signal, 'AI_RED')
                        else:
                            print(f"[BLOK] {ticker}: {reason}")

                # Parallel execution
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(WATCHLIST)) as executor:
                    futures = [executor.submit(scan_work, t, c) for t, c in WATCHLIST.items()]
                    concurrent.futures.wait(futures)
                
                manage_open_positions()
                time.sleep(15) # Optimized sleep
            else:
                manage_open_positions()
                if now.hour == 20 and now.minute == 0:
                    daily_summary()
                    
                # Update Cache for UI (Passive)
                for tkr in WATCHLIST:
                    if tkr not in bot_status_cache: bot_status_cache[tkr] = {'signal': 'BEKLEYOR', 'trades': 0, 'pnl': 0}
                    bot_status_cache[tkr]['signal'] = 'KILL_ZONE_DISI'
                
                print(f"[SLEEP] Kill zone disinda: {now.strftime('%H:%M UTC')}")
                time.sleep(300)
        except Exception as e:
            print(f"[HATA] Genel hata: {e}")
            time.sleep(60)

@app.route('/')
def serve_index():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(base_dir, 'index.html')

@app.route('/backtest')
def serve_backtest():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(base_dir, 'backtest.html')

@app.route('/api/toggle_bot', methods=['POST'])
def toggle_bot():
    global bot_active
    bot_active = not bot_active
    return jsonify({"bot_active": bot_active})

@app.route('/api/status', methods=['GET'])
def api_status():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(base_dir, 'trades_log.csv')
    logs = []
    if os.path.exists(log_file):
        df = pd.read_csv(log_file)
        logs = df.tail(10).to_dict('records')
        
    return jsonify({
        "status": bot_status_cache,
        "logs": logs,
        "scan_logs": scan_logs,
        "bot_active": bot_active
    })

@app.route('/api/portfolio', methods=['GET'])
def get_portfolio():
    return jsonify({
        "balance": "100000.00",
        "cash": "100000.00",
        "buying_power": "200000.00",
        "positions": [],
        "bot_active": bot_active,
        "env": "OANDA DEMO"
    })

@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.json
    system_prompt = data.get("system", "")
    messages = data.get("messages", [])
    
    user_content = messages[0]["content"] if messages else ""
    ticker = user_content.split(" ")[0].upper()
    
    try:
        df_m15 = get_oanda_bars(ticker, granularity='M15', count=100)
        df_m5 = get_oanda_bars(ticker, granularity='M5', count=100)
        
        if df_m5.empty or df_m15.empty:
            raise Exception("OANDA veri alinamadi.")
            
        last_m15 = df_m15.iloc[-1]
        df_m15['EMA_200'] = ta.ema(df_m15['Close'], length=200)
        bias_15 = "BULLISH" if last_m15['Close'] > last_m15.get('EMA_200', 0) else "BEARISH"
        
        amd_res = detect_amd_phases_v2(df_m5.tail(100))
        ts_res = find_turtle_soup_v2(df_m5.tail(60), lookback=20)
        
        status_v2 = f"AMD: {amd_res['direction'] if amd_res else 'Yok'}, TS: {'Var' if ts_res else 'Yok'}"
        current_price = float(df_m5.iloc[-1]['Close'])
        df_m5['ATR'] = ta.atr(df_m5['High'], df_m5['Low'], df_m5['Close'], length=14)
        atr = float(df_m5['ATR'].iloc[-1])
        
        market_data_str = f"OANDA ICT Analizi ({ticker}): Bias (M15): {bias_15}, V2 Sinyal: {status_v2}, Fiyat: {current_price}, ATR: {atr:.4f}"
    except Exception as e:
        market_data_str = f"Hata: {e}"
        
    enhanced_system_prompt = system_prompt + f"\n\nICT DATA: {market_data_str}"

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": enhanced_system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.7,
            response_format={ "type": "json_object" }
        )
        return jsonify({ "content": [{ "type": "text", "text": completion.choices[0].message.content }] })
    except Exception as e:
        return jsonify({"error": {"message": str(e) }}), 500

def start_bot_thread():
    t = threading.Thread(target=run_forever, daemon=True)
    t.start()
    print("[THREAD] Bot Thread Baslatildi")

if __name__ == '__main__':
    start_bot_thread()
    print("AI Hedge Fund + OANDA Trading Sunucusu Baslatiliyor...")
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)
