"""
==========================================================
  SINGULARITY V12 HFT AGGRESSIVE — CANLI BOT (1000 MUM SYNC)
==========================================================
Sistem: realistic_backtest_v8.py (HFT Mode) / V11 Aggressive
Performans Profili: ~300+ islem / Ay | %57-%68 Win Rate
Risk/Odul (RR): 1:1.5
Sinirlayici: Threshold = 20
Hafıza: 1000 Mum (Her 5dk'da bir Oanda ile senkronize)
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
from oandapyV20.endpoints import accounts

from oanda_data import download_oanda_candles
from ict_utils import apply_ict_v12_depth, get_smc_bias_v11
from database_manager import log_trade

# --- SETUP ---
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"), override=True)

OANDA_API_KEY    = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV        = os.getenv("OANDA_ENV", "practice")

api = API(access_token=OANDA_API_KEY, environment=OANDA_ENV)

# En Aktif Pariteler
SYMBOLS = ["EUR_USD", "GBP_USD", "XAU_USD", "USD_JPY", "USD_CAD"]

THRESHOLD = 20    # Agresif tetikleme puani
RISK_PCT  = 0.01  # %1 Risk
RR_RATIO  = 1.5   # 1.5 R/R

def open_hft_order(sym, direction, entry, sl, tp):
    try:
        r_acc = accounts.AccountSummary(OANDA_ACCOUNT_ID)
        api.request(r_acc)
        balance = float(r_acc.response.get('account', {}).get('balance', 1000.0))
        risk_amount = balance * RISK_PCT 
        
        sl_pts = abs(entry - sl)
        if sl_pts == 0: return False
        
        # Units calculation logic remains same
        if "XAU" in sym:
            units = int(risk_amount / sl_pts / 100)
            if units < 1: units = 1
        elif "JPY" in sym:
            units = int(risk_amount / sl_pts * 100)
        else:
            units = int(risk_amount / sl_pts)
            
        if direction == "SELL": units = -units

        data = {
            "order": {
                "instrument": sym, "units": str(units), "type": "MARKET",
                "stopLossOnFill": {"price": f"{sl:.5f}"},
                "takeProfitOnFill": {"price": f"{tp:.5f}"}
            }
        }
        
        print(f"🚀 [HFT SCALP] {sym} {direction} | E:{entry:.5f} SL:{sl:.5f} TP:{tp:.5f}")
        api.request(orders.OrderCreate(OANDA_ACCOUNT_ID, data=data))
        
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
    print("    SINGULARITY HFT AGGRESSIVE (1000 MUM SYNC)  ")
    print("=======================================================")
    
    hist_5m   = {}
    htf_bias  = {s: "NEUTRAL" for s in SYMBOLS}
    last_bar  = {s: None for s in SYMBOLS}

    # 1. İlk Dolum
    for sym in SYMBOLS:
        print(f"  İlk Senkronizasyon (1000 Mum): {sym}...")
        hist_5m[sym] = download_oanda_candles(sym, "M5", count=1000)
        df1h = download_oanda_candles(sym, "H1", count=100)
        htf_bias[sym] = get_smc_bias_v11(df1h.tail(20)) if not df1h.empty else "NEUTRAL"
        last_bar[sym] = hist_5m[sym].index[-1] if not hist_5m[sym].empty else None

    last_htf_upd = datetime.now()

    r = pricing.PricingStream(accountID=OANDA_ACCOUNT_ID, params={"instruments": ",".join(SYMBOLS)})
    def get_stream(): return api.request(r)

    for msg in get_stream():
        now_utc = datetime.now(timezone.utc)
        
        # 2. HTF Bias Yenilemesi (1 Saatte Bir)
        if (datetime.now() - last_htf_upd).total_seconds() > 3600:
            for s in SYMBOLS:
                df1h = download_oanda_candles(s, "H1", count=100)
                htf_bias[s] = get_smc_bias_v11(df1h.tail(20)) if not df1h.empty else htf_bias[s]
            last_htf_upd = datetime.now()
            print(f"🔄 HTF Bias Güncellendi: {htf_bias}")

        if msg.get('type') != 'PRICE': continue

        sym = msg['instrument']
        price = float(msg['bids'][0]['price'])

        # Real-time update (streaming candle)
        nr = pd.DataFrame([{"Time": now_utc, "Open": price, "High": price, "Low": price, "Close": price, "Volume": 1}]).set_index("Time")
        hist_5m[sym] = pd.concat([hist_5m[sym], nr]).tail(1001)

        # 3. Bar Kapanışı Tarama (5-min intervals)
        cur_bar = now_utc.replace(second=0, microsecond=0)
        cur_bar = cur_bar - timedelta(minutes=cur_bar.minute % 5)

        if last_bar[sym] and cur_bar > last_bar[sym]:
            # KULLANICI TALEBI: 1000 mum her zaman aktif sekilde guncellensin (Hard Sync)
            print(f"⌛ Bar Kapandi ({sym}). 1000 mum taze verisi cekiliyor...")
            hist_5m[sym] = download_oanda_candles(sym, "M5", count=1000)
            last_bar[sym] = cur_bar
            
            df = hist_5m[sym].copy()
            if len(df) < 50: continue

            try:
                # 1000 mum uzerinden ICT analizi
                df = apply_ict_v12_depth(df)
            except Exception as e:
                print(f"Hata indicators: {e}"); continue
                
            row = df.iloc[-1]
            bias = htf_bias[sym]
            
            # SCORE SYSTEM
            score = 0
            if row.get('FVG_Bull'): score += 25
            if row.get('TurtleSoup_Bull'): score += 20
            if row.get('IFVG_Bull'): score += 22
            if row.get('VI_Bull'): score += 15
            
            if row.get('FVG_Bear'): score -= 25
            if row.get('TurtleSoup_Bear'): score -= 20
            if row.get('IFVG_Bear'): score -= 22
            if row.get('VI_Bear'): score -= 15
            
            # PD Array 
            past_25 = df.tail(25)
            eq = (past_25['High'].max() + past_25['Low'].min()) / 2
            
            # ATR (Dinamik Risk)
            atr_val = ta.atr(df['High'], df['Low'], df['Close'], length=14).iloc[-1]
            if pd.isna(atr_val): atr_val = price * 0.001
            
            # ENTRY
            if score >= THRESHOLD and bias == "BULLISH" and price < eq:
                sl_dist = atr_val * 1.5
                sl = price - sl_dist
                tp = price + (sl_dist * RR_RATIO)
                open_hft_order(sym, "BUY", price, sl, tp)
                
            elif score <= -THRESHOLD and bias == "BEARISH" and price > eq:
                sl_dist = atr_val * 1.5
                sl = price + sl_dist
                tp = price - (sl_dist * RR_RATIO)
                open_hft_order(sym, "SELL", price, sl, tp)
                
        await asyncio.sleep(0.01)

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main_loop())
        except Exception as e:
            print(f"HATA: {e}"); import time; time.sleep(5)
