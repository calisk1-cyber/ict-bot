"""
Backtest: Aralik 2024
Strateji: EMA 9/21 Crossover + Volume Spike + AI Sim (bot4_trader.py ile birebir)
"""
import os, sys
import pandas as pd
import pandas_ta as ta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from oanda_data import download_oanda_candles

SYMBOLS      = ["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD", "USD_CAD"]
FROM_5M      = "2024-12-01T00:00:00Z"
TO_5M        = "2024-12-31T23:59:00Z"
FROM_1H      = "2024-11-01T00:00:00Z"
INIT_BAL     = 1000.0
RISK         = 0.01   # %1

def ai_sim(action, trend, rsi, hour):
    """AI onayini simule eder: Kill Zone + Trend + RSI"""
    kill = (7 <= hour <= 10) or (13 <= hour <= 16)
    tr   = (action == "LONG"  and "BULL" in trend) or \
           (action == "SHORT" and "BEAR" in trend)
    rsi_ok = not (action == "LONG" and rsi > 75) and not (action == "SHORT" and rsi < 25)
    return kill and tr and rsi_ok

def main():
    print("=" * 58)
    print("  ARALIK 2024 BACKTEST  |  EMA9/21 + VOL + AI-SIM")
    print("=" * 58)

    grand_net = 0.0
    grand_total = 0
    grand_wins  = 0

    for sym in SYMBOLS:
        print(f"\n--- {sym} ---")
        df5 = download_oanda_candles(sym, "M5", from_time=FROM_5M, to_time=TO_5M)
        dfH = download_oanda_candles(sym, "H1", from_time=FROM_1H, to_time=TO_5M)
        if df5.empty or dfH.empty:
            print("  VERI YOK"); continue

        df5["EMA9"]  = ta.ema(df5["Close"], length=9)
        df5["EMA21"] = ta.ema(df5["Close"], length=21)
        df5["ATR"]   = ta.atr(df5["High"], df5["Low"], df5["Close"], length=14)
        df5["RSI"]   = ta.rsi(df5["Close"], length=14)
        df5["VSMA"]  = ta.sma(df5["Volume"], length=20)

        dfH["EMA200"] = ta.ema(dfH["Close"], length=200)

        bal     = INIT_BAL
        trades  = []
        active  = None

        for i in range(25, len(df5) - 1):
            row  = df5.iloc[i]
            prev = df5.iloc[i - 1]
            ts   = df5.index[i]
            price = float(row["Close"])

            # ----- EXIT -----
            if active:
                t = active
                if t["dir"] == "LONG":
                    if price <= t["sl"]:
                        loss = bal * RISK
                        bal -= loss
                        trades.append(("SL", ts, -loss))
                        active = None
                    elif price >= t["tp"]:
                        gain = bal * RISK * 2.0
                        bal += gain
                        trades.append(("TP", ts, gain))
                        active = None
                else:
                    if price >= t["sl"]:
                        loss = bal * RISK
                        bal -= loss
                        trades.append(("SL", ts, -loss))
                        active = None
                    elif price <= t["tp"]:
                        gain = bal * RISK * 2.0
                        bal += gain
                        trades.append(("TP", ts, gain))
                        active = None
                continue   # Acik islemde yeni sinyal arama

            # ----- FILTERS -----
            vsma = row["VSMA"]
            if pd.isna(vsma) or float(row["Volume"]) < float(vsma) * 1.5: continue

            atr = float(row["ATR"]) if not pd.isna(row["ATR"]) else price * 0.001
            rsi = float(row["RSI"]) if not pd.isna(row["RSI"]) else 50.0

            past_h = dfH[dfH.index <= ts]
            if past_h.empty or pd.isna(past_h["EMA200"].iloc[-1]): continue
            trend = "BULLISH" if float(past_h["Close"].iloc[-1]) > float(past_h["EMA200"].iloc[-1]) else "BEARISH"

            e9 = float(row["EMA9"]); e21 = float(row["EMA21"])
            p9 = float(prev["EMA9"]); p21 = float(prev["EMA21"])
            if any(pd.isna([e9, e21, p9, p21])): continue

            # ----- SIGNAL -----
            sig = None
            if e9 > e21 and p9 <= p21: sig = "LONG"
            elif e9 < e21 and p9 >= p21: sig = "SHORT"
            if not sig: continue

            hour = ts.hour if hasattr(ts, "hour") else 0
            if not ai_sim(sig, trend, rsi, hour): continue

            # ----- ENTRY -----
            sl = price - atr * 1.5 if sig == "LONG" else price + atr * 1.5
            tp = price + atr * 3.0 if sig == "LONG" else price - atr * 3.0
            active = {"dir": sig, "sl": sl, "tp": tp}

        # ----- SYM REPORT -----
        if trades:
            wins = sum(1 for t in trades if t[0] == "TP")
            net  = bal - INIT_BAL
            wr   = wins / len(trades) * 100
            print(f"  Islem    : {len(trades)}")
            print(f"  Kazanan  : {wins} | Kaybeden: {len(trades)-wins}")
            print(f"  Win Rate : {wr:.1f}%")
            print(f"  Net PnL  : ${net:+.2f}")
            grand_net   += net
            grand_total += len(trades)
            grand_wins  += wins
        else:
            print("  Islem acilamadi.")

    # ----- GRAND REPORT -----
    print("\n" + "=" * 58)
    print("  GENEL SONUC - ARALIK 2024")
    print("=" * 58)
    print(f"  Toplam Islem : {grand_total}")
    if grand_total > 0:
        print(f"  Kazananlar   : {grand_wins}")
        print(f"  Kaybedenler  : {grand_total - grand_wins}")
        print(f"  Genel WR     : {grand_wins/grand_total*100:.1f}%")
    print(f"  Toplam Net   : ${grand_net:+.2f}")
    print("=" * 58)

if __name__ == "__main__":
    main()
