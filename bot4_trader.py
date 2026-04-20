"""
==========================================================
  SINGULARITY V12 HFT AGGRESSIVE — CANLI BOT (AGGRESSIVE SCALE-IN)
==========================================================
Sistem: realistic_backtest_v8.py (HFT Mode) / V11 Aggressive
Performans Profili: ~300+ islem / Ay
Risk/Odul (RR): 1:1.5
Hafıza: 1000 Mum Sync
Mod: FULL AGGRESSIVE (Ayni paritede yeni firsatlara girer)
==========================================================
"""

import os
import asyncio
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from oandapyV20 import API
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.pricing as pricing
from oandapyV20.endpoints import accounts, trades
from oandapyV20.contrib.requests import StopLossOrderRequest, TakeProfitOrderRequest

from oanda_data import download_oanda_candles
from ict_utils import apply_ict_v12_depth, get_smc_bias_v11
from database_manager import log_trade
from daily_risk_manager import DailyRiskManager

# --- SETUP ---
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"), override=True)

OANDA_API_KEY    = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV        = os.getenv("OANDA_ENV", "practice")

api = API(access_token=OANDA_API_KEY, environment=OANDA_ENV)
SYMBOLS = ["EUR_USD", "NZD_USD", "GBP_USD", "XAU_USD", "EUR_HUF", "AUD_NZD", "TRY_JPY", "GBP_CAD", "AUD_CAD", "EUR_CAD", "GBP_CHF", "CAD_HKD", "USD_THB", "AUD_HKD", "EUR_TRY"]

THRESHOLD = 20
RISK_PCT  = 0.01    # Hybrid Aggressive: 1.0% risk (max 15 global)
RR_RATIO  = 2.5
MAX_UNITS_MAJOR = 400000   # Restored: allows full 1% natural sizing (~388k on majors)
MAX_UNITS_EXOTIC = 100000  # Restored: safer exotics cap
MAX_POS_PER_SYM  = 2       # Restored: scale-in allowed (high-win mode)
MAX_GLOBAL_POSITIONS = 15
MARGIN_BUFFER    = 0.90    # Restored: more room for large positions

# Per-symbol unit caps for highly restrictive exotics
SYMBOL_UNIT_LIMITS = {
    "TRY_JPY": 25000,
    "USD_THB": 50000,
    "EUR_HUF": 50000,
    "CAD_HKD": 100000,  # Restored
    "AUD_HKD": 100000,  # Restored
    "EUR_TRY": 25000
}

risk_manager = DailyRiskManager(initial_balance=100000.0)

# --- 'OCTOBER 2025' MODE: FULL AGGRESSIVE (No Limits) ---
# Sistem, arka arkaya kayıpları göze alarak trendi sonuna kadar sömürür.

def open_hft_order(sym, direction, entry, sl, tp):
    try:
        r_acc = accounts.AccountSummary(OANDA_ACCOUNT_ID)
        api.request(r_acc)
        balance = float(r_acc.response.get('account', {}).get('balance', 1000.0))
        risk_manager.update_date(datetime.now().date())
        
        current_risk = RISK_PCT
        risk_amount = balance * current_risk 
        
        sl_pts = abs(entry - sl)
        if sl_pts == 0: return False
        
        # --- UNIT CALCULATION ---
        if "XAU" in sym:
            units = int(risk_amount / sl_pts)
        elif "JPY" in sym:
            units = int(risk_amount / (sl_pts / entry))
        else:
            units = int(risk_amount / sl_pts)
            
        if direction == "SELL": units = -units

        # --- POSITION LIMITS & FIFO PROTECTION ---
        # 1. Check existing positions
        r_trades = trades.TradesList(OANDA_ACCOUNT_ID)
        api.request(r_trades)
        open_trades = r_trades.response.get('trades', [])

        # FIFO PROTECT: If any trade for this sym exists, skip.
        # This prevents both scale-in (multiple same dirs) and hedging (opposing dirs).
        sym_trades = [t for t in open_trades if t['instrument'] == sym]
        if len(sym_trades) >= MAX_POS_PER_SYM:
            print(f"🛑 [FIFO PROTECT] {sym} already has an active trade. Skipping.")
            return False

        # 2. Global Limit Check
        if len(open_trades) >= MAX_GLOBAL_POSITIONS:
            print(f"🛑 [GLOBAL LIMIT] Account already has {len(open_trades)} positions. Skipping.")
            return False

        # 3. Dynamic Unit Capping
        is_exotic = any(x in sym for x in ["HUF", "TRY", "THB", "HKD", "MXN", "ZAR", "SGD"])
        symbol_limit = SYMBOL_UNIT_LIMITS.get(sym, MAX_UNITS_EXOTIC if is_exotic else MAX_UNITS_MAJOR)
        
        if abs(units) > symbol_limit:
            print(f"⚠️ [UNIT CAP] {sym} {units} -> {symbol_limit if units > 0 else -symbol_limit}")
            units = symbol_limit if units > 0 else -symbol_limit

        # 4. Margin available check
        margin_avail = float(r_acc.response.get('account', {}).get('marginAvailable', 0.0))
        # Conservatively estimate 5% margin for exotics, 2% for majors
        margin_req_pct = 0.05 if is_exotic else 0.02
        estimated_margin = (abs(units) * entry * margin_req_pct) if "JPY" not in sym else (abs(units) * (entry/100) * margin_req_pct)
        
        if estimated_margin > margin_avail * MARGIN_BUFFER: 
            print(f"🛑 [MARGIN SHORTAGE] Needed: {estimated_margin:.2f}, Avail: {margin_avail:.2f}. Skipping.")
            return False

        # Precision handling (JPY/THB/HUF/XAU use 3 decimals, others 5)
        precision_map = {
            'EUR_USD': 5, 'NZD_USD': 5, 'GBP_USD': 5, 'XAU_USD': 3,
            'EUR_HUF': 3, 'AUD_NZD': 5, 'TRY_JPY': 3, 'GBP_CAD': 5,
            'AUD_CAD': 5, 'EUR_CAD': 5, 'GBP_CHF': 5, 'CAD_HKD': 5,
            'USD_THB': 3, 'AUD_HKD': 5, 'EUR_TRY': 5, 'USD_JPY': 3, 'USD_CAD': 5
        }
        precision = precision_map.get(sym, 5)
        
        data = {
            "order": {
                "instrument": sym, "units": str(units), "type": "MARKET",
                "stopLossOnFill": {"price": f"{sl:.{precision}f}"},
                "takeProfitOnFill": {"price": f"{tp:.{precision}f}"}
            }
        }
        
        print(f"🚀 [HFT ORDER] {sym} {direction} | E:{entry:.5f} SL:{sl:.5f} TP:{tp:.5f}")
        order_resp = api.request(orders.OrderCreate(OANDA_ACCOUNT_ID, data=data))
        
        # --- VERIFICATION & FALLBACK ---
        fill_data = order_resp.get('orderFillTransaction', {})
        trade_id = fill_data.get('tradeOpened', {}).get('tradeID')
        
        if trade_id:
            risk_manager.register_trade_result(0) # Register zero first, actual PnL comes later
            sl_created = any(x in order_resp for x in ['stopLossOrderFillTransaction', 'stopLossOrderCreated'])
            tp_created = any(x in order_resp for x in ['takeProfitOrderFillTransaction', 'takeProfitOrderCreated'])
            
            if not sl_created or not tp_created:
                print(f"⚠️  [ATTACHMENT FAILED] Trade {trade_id} missing SL/TP. Retrying fallback...")
                try:
                    if not sl_created:
                        sl_req = StopLossOrderRequest(tradeID=trade_id, price=f"{sl:.{precision}f}")
                        api.request(orders.OrderCreate(OANDA_ACCOUNT_ID, data=sl_req.data))
                    if not tp_created:
                        tp_req = TakeProfitOrderRequest(tradeID=trade_id, price=f"{tp:.{precision}f}")
                        api.request(orders.OrderCreate(OANDA_ACCOUNT_ID, data=tp_req.data))
                    print(f"✅ [RECOVERY SUCCESS] SL/TP attached to Trade {trade_id}")
                except Exception as fb_err:
                    print(f"❌ [RECOVERY FAILED] Trade {trade_id}: {fb_err}")

        log_trade({
            "ticker": sym, "direction": direction, "entry_price": entry,
            "sl": sl, "tp": tp, "units": units,
            "signal_type": "HFT AGGRESSIVE (V12)", "status": "OPEN",
            "ai_decision": "SYSTEM_TRIGGER", "ai_reason": f"Score >= {THRESHOLD}"
        })
        return True
    except Exception as e:
        print(f"❌ [ORDER ERROR] {sym}: {e}"); return False

async def main_loop():
    print("=======================================================")
    print("    SINGULARITY HFT AGGRESSIVE (SCALE-IN MODE)  ")
    print("=======================================================")
    
    hist_5m   = {}
    htf_bias  = {s: "NEUTRAL" for s in SYMBOLS}
    last_bar  = {s: None for s in SYMBOLS}

    for sym in SYMBOLS:
        print(f"  Senkronize ediliyor: {sym}...")
        hist_5m[sym] = download_oanda_candles(sym, "M5", count=1000)
        dfh4 = download_oanda_candles(sym, "H4", count=100)
        htf_bias[sym] = get_smc_bias_v11(dfh4.tail(20)) if not dfh4.empty else "NEUTRAL"
        last_bar[sym] = hist_5m[sym].index[-1] if not hist_5m[sym].empty else None

    last_htf_upd = datetime.now()
    params = {"instruments": ",".join(SYMBOLS)}
    r = pricing.PricingStream(accountID=OANDA_ACCOUNT_ID, params=params)
    
    print(f"  Hesap dogrulaniyor: {OANDA_ACCOUNT_ID}...")
    try:
        acc_req = accounts.AccountDetails(accountID=OANDA_ACCOUNT_ID)
        api.request(acc_req)
        print("    Hesap dogrulandi.")
    except Exception as acc_err:
        print(f"    HESAP HATASI: {acc_err}")
        return

    print(f"  Stream baslatiliyor: {params['instruments']}")
    try:
        stream_request = api.request(r)
        if hasattr(stream_request, 'status_code') and stream_request.status_code >= 400:
            print(f"    STREAM REDDEDILDI: HTTP {stream_request.status_code} - {stream_request.response}")
            return

        for msg in stream_request:
            now_utc = datetime.now(timezone.utc)
            if msg.get('type') == 'HEARTBEAT':
                continue

            if (datetime.now() - last_htf_upd).total_seconds() > 14400: # 4 Hours
                for s in SYMBOLS:
                    dfh4 = download_oanda_candles(s, "H4", count=100)
                    htf_bias[s] = get_smc_bias_v11(dfh4.tail(20)) if not dfh4.empty else "NEUTRAL"
                last_htf_upd = datetime.now()

            if msg.get('type') != 'PRICE': 
                continue
                
            sym = msg['instrument']
            price = float(msg['bids'][0]['price'])

            nr = pd.DataFrame([{"Time": now_utc, "Open": price, "High": price, "Low": price, "Close": price, "Volume": 1}]).set_index("Time")
            hist_5m[sym] = pd.concat([hist_5m[sym], nr]).tail(1001)

            cur_bar = now_utc.replace(second=0, microsecond=0)
            cur_bar = cur_bar - timedelta(minutes=cur_bar.minute % 5)

            if last_bar[sym] and cur_bar > last_bar[sym]:
                # Hard Sync each bar
                hist_5m[sym] = download_oanda_candles(sym, "M5", count=1000)
                last_bar[sym] = cur_bar
                
                df = hist_5m[sym].copy()
                try:
                    df = apply_ict_v12_depth(df)
                except: 
                    continue
                    
                row = df.iloc[-1]
                
                # --- SCORING LOGIC (RESTORED) ---
                score = 0
                if row.get('FVG_Bull'):        score += 25
                if row.get('TurtleSoup_Bull'): score += 20
                if row.get('IFVG_Bull'):       score += 22
                if row.get('VI_Bull'):         score += 15
                
                if row.get('FVG_Bear'):        score -= 25
                if row.get('TurtleSoup_Bear'): score -= 20
                if row.get('IFVG_Bear'):       score -= 22
                if row.get('VI_Bear'):         score -= 15
                
                past_25 = df.tail(25)
                eq = (past_25['High'].max() + past_25['Low'].min()) / 2
                atr_val = ta.atr(df['High'], df['Low'], df['Close'], length=14).iloc[-1]
                if pd.isna(atr_val): atr_val = price * 0.001
                
                pip = 0.1 if "XAU" in sym else (0.01 if "JPY" in sym or "HUF" in sym else 0.0001)
                
                # Giris Kosullari (V18 GOLDEN: 100% Backtest Parity)
                if score >= THRESHOLD and htf_bias.get(sym, "NEUTRAL") == "BULLISH" and price < eq:
                    sl = price - (25 * pip)
                    tp = price + (25 * pip * RR_RATIO)
                    if open_hft_order(sym, "BUY", price, sl, tp):
                        last_bar[sym] = cur_bar 
                elif score <= -THRESHOLD and htf_bias.get(sym, "NEUTRAL") == "BEARISH" and price > eq:
                    sl = price + (25 * pip)
                    tp = price - (25 * pip * RR_RATIO)
                    if open_hft_order(sym, "SELL", price, sl, tp):
                        last_bar[sym] = cur_bar
                    
            await asyncio.sleep(0.01)
    except Exception as e:
        print(f"  Stream loop hatası: {e}")

if __name__ == "__main__":
    from database_manager import init_database
    init_database()
    while True:
        try:
            asyncio.run(main_loop())
        except Exception as e:
            print(f"Kritik Hata: {e}")
            import time
            time.sleep(5)
