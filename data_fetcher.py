import yfinance as yf
import pandas as pd
import pandas_ta as ta
import datetime
import traceback
try:
    import fear_and_greed
except ImportError:
    fear_and_greed = None

def get_fear_and_greed():
    if fear_and_greed:
        try:
            return fear_and_greed.get().value
        except:
            return "N/A (CNN sitesine erişilemiyor)"
    return "N/A"

def fetch_market_data(ticker_symbol):
    print(f"[{ticker_symbol}] Gerçek zamanlı borsa ve makro verileri çekiliyor...")
    result = {"symbol": ticker_symbol}
    
    try:
        # 1. Hisse Senedi Verisi (1 Günlük ve 5 Dakikalık)
        ticker = yf.Ticker(ticker_symbol)
        
        # 1D OHLC (Son 1 Yıl)
        df_1d = ticker.history(period="1y", interval="1d")
        if not df_1d.empty:
            result['daily_close'] = df_1d['Close'].iloc[-1]
            df_1d['EMA_50'] = ta.ema(df_1d['Close'], length=50)
            df_1d['EMA_200'] = ta.ema(df_1d['Close'], length=200)
            if len(df_1d) >= 50 and not pd.isna(df_1d['EMA_50'].iloc[-1]):
                result['daily_trend_vs_50EMA'] = "Bullish" if df_1d['Close'].iloc[-1] > df_1d['EMA_50'].iloc[-1] else "Bearish"
            else:
                result['daily_trend_vs_50EMA'] = "Unknown"
        else:
            result['daily_trend_vs_50EMA'] = "Data Error"
            
        # 5M OHLC (Son 5 Gün)
        df_5m = ticker.history(period="5d", interval="5m")
        if not df_5m.empty:
            df_5m['EMA_9'] = ta.ema(df_5m['Close'], length=9)
            df_5m['EMA_21'] = ta.ema(df_5m['Close'], length=21)
            df_5m['RSI_14'] = ta.rsi(df_5m['Close'], length=14)
            df_5m['ATR_14'] = ta.atr(df_5m['High'], df_5m['Low'], df_5m['Close'], length=14)
            
            # MACD
            macd = ta.macd(df_5m['Close'])
            if macd is not None and not macd.empty:
                df_5m = pd.concat([df_5m, macd], axis=1)
                macd_col = [c for c in macd.columns if c.startswith('MACD_')][0]
                result['macd_5m'] = df_5m[macd_col].iloc[-1]
            else:
                result['macd_5m'] = "N/A"
                
            # FVG (Fair Value Gap) Tespiti - En son oluşan 3 FVG'yi bulma (Güncel 5m momları)
            fvgs = []
            for i in range(2, min(50, len(df_5m))):
                idx = -i
                high_1 = df_5m['High'].iloc[idx-2]
                low_1 = df_5m['Low'].iloc[idx-2]
                high_3 = df_5m['High'].iloc[idx]
                low_3 = df_5m['Low'].iloc[idx]
                
                # Bullish FVG: 1. mumun tepesi ile 3. mumun dibi arasındaki boşluk
                if low_3 > high_1:
                    fvgs.append({"type": "bullish", "gap": f"{high_1:.2f} - {low_3:.2f}", "time": str(df_5m.index[idx])})
                # Bearish FVG: 3. mumun tepesi ile 1. mumun dibi arasındaki boşluk
                elif high_3 < low_1:
                    fvgs.append({"type": "bearish", "gap": f"{low_3:.2f} - {high_1:.2f}", "time": str(df_5m.index[idx])})
            
            result['current_price'] = df_5m['Close'].iloc[-1]
            result['ema_9_5m'] = df_5m['EMA_9'].iloc[-1]
            result['ema_21_5m'] = df_5m['EMA_21'].iloc[-1]
            result['rsi_14_5m'] = df_5m['RSI_14'].iloc[-1]
            result['atr_14_5m'] = df_5m['ATR_14'].iloc[-1]
            result['recent_fvgs_5m'] = fvgs[:3]  # En son 3 FVG
        
        # 2. VIX Endeksi (Korku / Volatilite endeksi)
        vix = yf.Ticker("^VIX").history(period="1d")
        result['vix'] = vix['Close'].iloc[-1] if not vix.empty else "N/A"
        
        # 3. Fear & Greed Index
        result['fear_greed_index'] = get_fear_and_greed()
        
        # 4. Şirket Makro/Mali Verileri
        info = ticker.info
        
        # Short Float Oranı
        short_float = info.get("shortPercentOfFloat")
        result['short_float_percent'] = (short_float * 100) if short_float else "N/A"
        
        # Yaklaşan Kazanç Raporu Tarihi (Earnings Date)
        et = info.get("earningsTimestamp")
        if et:
            dt = datetime.datetime.fromtimestamp(et)
            result['next_earnings_date'] = dt.strftime("%Y-%m-%d")
        else:
            result['next_earnings_date'] = "Bilinmiyor"
            
        print(f"[{ticker_symbol}] Veri çekme başarıyla tamamlandı.")
        return result
    except Exception as e:
        print(f"Data Fetch Error: {e}")
        traceback.print_exc()
        result['error'] = str(e)
        return result


def download_dukascopy_mtf(ticker='EURUSD', start='2025-01-01', end='2026-01-01'):
    """
    Dukascopy'den coklu zaman dilimi (MTF) verisini parcali indirir ve CSV olarak saklar.
    """
    import dukascopy_python as dp
    from datetime import datetime, timedelta
    import pandas as pd
    
    try:
        ticker_clean = ticker.replace("=X", "").replace(".X", "")
        start_dt = datetime.strptime(start, '%Y-%m-%d')
        end_dt = datetime.strptime(end, '%Y-%m-%d')
        
        timeframes = {
            '1h': dp.INTERVAL_HOUR_1,
            '4h': dp.INTERVAL_HOUR_4,
            '15m': dp.INTERVAL_MIN_15,
            '30m': dp.INTERVAL_MIN_30,
            '5m': dp.INTERVAL_MIN_5
        }
        
        print(f"\n[Dukascopy] MTF Chunked Download Baslatildi: {ticker_clean}")
        
        for label, dp_interval in timeframes.items():
            print(f"-> {label} indiriliyor...", end=" ", flush=True)
            curr_start = start_dt
            all_chunks = []
            
            while curr_start < end_dt:
                curr_end = min(curr_start + timedelta(days=30), end_dt)
                try:
                    data = dp.fetch(
                        instrument=ticker_clean,
                        interval=dp_interval,
                        offer_side=dp.OFFER_SIDE_BID,
                        start=curr_start,
                        end=curr_end
                    )
                    if data is not None and not data.empty:
                        all_chunks.append(data)
                except Exception as e:
                    # Encoding fix: remove weird chars from error msg
                    err_msg = str(e).encode('ascii', 'ignore').decode()
                    print(f"\n[!] Chunk Atlandi ({curr_start.date()}): {err_msg}")
                curr_start = curr_end
                
            if all_chunks:
                combined = pd.concat(all_chunks)
                combined = combined[~combined.index.duplicated(keep='last')]
                combined.columns = [col.capitalize() for col in combined.columns]
                # Filter out redundant headers if concat adds them (though dp.fetch usually returns clean DFs)
                # But to be safe, standard columns must exist
                filename = f"{ticker_clean.lower()}_{label}.csv"
                combined.to_csv(filename)
                print(f"Tamamlandi. ({len(combined)} bar)")
            else:
                print("HATA: Veri bulunamadi.")
                
        print("[SUCCESS] MTF Veri indirme islemi bitti.\n")
        return True
    except Exception as e:
        print(f"Dukascopy Error: {e}")
        return False
