import pandas as pd
import numpy as np
import pandas_ta as ta

import time
import pytz
from datetime import datetime, timedelta

def get_timeframes_for_period(period):
    mapping = {
        '7d':  {'signal':'1m',  'structure':'5m',  'bias':'15m'},
        '30d': {'signal':'5m',  'structure':'15m', 'bias':'1h'},
        '3mo': {'signal':'5m',  'structure':'15m', 'bias':'1h'},
        '6mo': {'signal':'5m',  'structure':'15m', 'bias':'1h'},
        '1y':  {'signal':'5m',  'structure':'15m', 'bias':'1h'},
        '5y':  {'signal':'15m', 'structure':'1h',  'bias':'1d'},
    }
    return mapping.get(period, {'signal': '5m', 'structure': '15m', 'bias': '1h'})

def download_full_history(ticker, months=12, interval='5m'):
    import pandas as pd
    import os
    from datetime import datetime, timedelta
    from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    
    API_KEY = os.getenv("ALPACA_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
    
    is_crypto = "/" in ticker or "BTC" in ticker or "ETH" in ticker
    if is_crypto: client = CryptoHistoricalDataClient(API_KEY, SECRET_KEY)
    else: client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
        
    all_data = []
    end = datetime.now()
    chunk_days = 90
    total_days = months * 30
    chunks = total_days // chunk_days + 1
    
    if interval == '1m': tf = TimeFrame(1, TimeFrameUnit.Minute)
    elif interval == '5m': tf = TimeFrame(5, TimeFrameUnit.Minute)
    elif interval == '15m': tf = TimeFrame(15, TimeFrameUnit.Minute)
    elif interval == '1h': tf = TimeFrame(1, TimeFrameUnit.Hour)
    else: tf = TimeFrame.Day
    
    for i in range(chunks):
        chunk_end = end - timedelta(days=i * chunk_days)
        chunk_start = chunk_end - timedelta(days=chunk_days)
        
        try:
            if is_crypto:
                req = CryptoBarsRequest(symbol_or_symbols=[ticker], timeframe=tf, start=chunk_start, end=chunk_end)
                bars = client.get_crypto_bars(req)
            else:
                req = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=tf, start=chunk_start, end=chunk_end)
                bars = client.get_stock_bars(req)
                
            if not bars.df.empty:
                df = bars.df.loc[ticker].copy()
                df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
                all_data.append(df)
                print(f"[{ticker}] Parca {i+1}/{chunks} idirildi: {chunk_start.date()} -> {chunk_end.date()} ({len(df)} mum)")
        except Exception as e:
            print(f"[{ticker}] Parca {i+1} atlandi: {e}")
            continue
            
    if not all_data:
        raise Exception("Veri indirilemedi")
        
    combined = pd.concat(all_data)
    combined = combined[~combined.index.duplicated(keep='last')]
    combined = combined.sort_index()
    
    if isinstance(combined.columns, pd.MultiIndex):
        combined.columns = combined.columns.droplevel(1)
        
    return combined

# === MARKET REGIME FILTER ===

REGIME_RULES = {
    'HIGH_VOLATILITY': {
        'trade': False,
        'reason': 'VIX > 30'
    },
    'CHOPPY': {
        'trade': True,
        'min_score': 75,
        'risk': 0.005
    },
    'TRENDING_UP': {
        'trade': True,
        'min_score': 50,
        'risk': 0.01,
        'only_direction': 'LONG'
    },
    'TRENDING_DOWN': {
        'trade': True,
        'min_score': 50,
        'risk': 0.01,
        'only_direction': 'SHORT'
    },
    'NEUTRAL': {
        'trade': True,
        'min_score': 65,
        'risk': 0.0075
    }
}

def calculate_adx(df, period=14):
    """ADX hesapla (Average Directional Index)."""
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    plus_dm = high.diff()
    minus_dm = low.diff().abs() * -1
    
    plus_dm = plus_dm.where((plus_dm > minus_dm.abs()) & (plus_dm > 0), 0)
    minus_dm = minus_dm.abs().where((minus_dm.abs() > plus_dm) & (minus_dm.abs() > 0), 0)
    
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.rolling(window=period).mean()
    
    return adx.iloc[-1] if len(adx.dropna()) > 0 else 0

def get_market_regime(df_daily, vix_close=None):
    """Piyasa rejimini belirle: EMA200, ADX, VIX."""
    if df_daily is None or df_daily.empty or len(df_daily) < 201:
        return 'NEUTRAL'
    
    ema200 = df_daily['Close'].ewm(span=200).mean()
    price = float(df_daily['Close'].iloc[-1])
    adx = calculate_adx(df_daily, period=14)
    
    if vix_close is not None:
        if vix_close > 30:
            return 'HIGH_VOLATILITY'
        elif vix_close > 20 and adx < 20:
            return 'CHOPPY'
    
    if price > float(ema200.iloc[-1]) and adx > 25:
        return 'TRENDING_UP'
    elif price < float(ema200.iloc[-1]) and adx > 25:
        return 'TRENDING_DOWN'
    else:
        return 'NEUTRAL'

def is_kill_zone(timestamp):
    if timestamp.tzinfo is not None:
        tz = timestamp.astimezone(pytz.UTC)
    else:
        # Assume input was UTC if naive
        tz = pytz.UTC.localize(timestamp) if hasattr(pytz, 'UTC') else timestamp
        
    hm = tz.hour * 100 + tz.minute
    
    # Londra: 07:00-10:00 UTC
    if 700 <= hm <= 1000:
        return "LONDRA"
    # NY: 13:00-16:00 UTC
    if 1300 <= hm <= 1600:
        # Silver Bullet: 14:00-15:00 UTC
        if 1400 <= hm <= 1500:
            return "SILVER_BULLET"
        return "NEW_YORK"
        
    return False

def find_fvg(df):
    df = df.copy()
    df['FVG_Bull'] = df['Low'] > df['High'].shift(2)
    df['FVG_Bear'] = df['High'] < df['Low'].shift(2)
    
    df['FVG_Bull_Top'] = np.where(df['FVG_Bull'], df['Low'], np.nan)
    df['FVG_Bull_Bottom'] = np.where(df['FVG_Bull'], df['High'].shift(2), np.nan)
    
    df['FVG_Bear_Bottom'] = np.where(df['FVG_Bear'], df['High'], np.nan)
    df['FVG_Bear_Top'] = np.where(df['FVG_Bear'], df['Low'].shift(2), np.nan)
    return df

def find_order_blocks(df):
    df = df.copy()
    if 'ATR_14' not in df.columns:
         df['ATR_14'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
         
    bob_price = np.nan
    bear_ob_price = np.nan
    
    ob_bull_s = pd.Series(np.nan, index=df.index)
    ob_bear_s = pd.Series(np.nan, index=df.index)
    
    body = (df['Close'] - df['Open']).abs()
    is_bull = df['Close'] > df['Open']
    is_bear = df['Close'] < df['Open']
    
    for i in range(14, len(df)):
        atr = df['ATR_14'].iloc[i]
        if pd.isna(atr): continue
        if is_bull.iloc[i] and body.iloc[i] > (atr * 1.5):
            for j in range(i-1, max(-1, i-10), -1):
                if is_bear.iloc[j]:
                    bob_price = df['Low'].iloc[j]
                    break
        if is_bear.iloc[i] and body.iloc[i] > (atr * 1.5):
            for j in range(i-1, max(-1, i-10), -1):
                if is_bull.iloc[j]:
                    bear_ob_price = df['High'].iloc[j]
                    break
        ob_bull_s.iloc[i] = bob_price
        ob_bear_s.iloc[i] = bear_ob_price
        
    df['Bullish_OB_Price'] = ob_bull_s
    df['Bearish_OB_Price'] = ob_bear_s
    return df

def find_bos_choch(df):
    df = df.copy()
    sh_price = np.nan
    sl_price = np.nan
    
    sh_series = pd.Series(np.nan, index=df.index)
    sl_series = pd.Series(np.nan, index=df.index)
    
    for i in range(10, len(df)):
        high_i5 = df['High'].iloc[i-5]
        low_i5 = df['Low'].iloc[i-5]
        
        is_sh = True
        is_sl = True
        for j in range(i-10, i+1):
            if j == i-5: continue
            if df['High'].iloc[j] >= high_i5: is_sh = False
            if df['Low'].iloc[j] <= low_i5: is_sl = False
            
        if is_sh: sh_price = high_i5
        if is_sl: sl_price = low_i5
        
        sh_series.iloc[i] = sh_price
        sl_series.iloc[i] = sl_price
        
    df['Swing_High'] = sh_series.ffill()
    df['Swing_Low'] = sl_series.ffill()
    
    df['BOS_Bull'] = (df['Close'] > df['Swing_High']) & (df['Close'].shift(1) <= df['Swing_High'].shift(1))
    df['BOS_Bear'] = (df['Close'] < df['Swing_Low']) & (df['Close'].shift(1) >= df['Swing_Low'].shift(1))
    return df

def find_ifvg(df):
    df = df.copy()
    df['iFVG_Bull'] = False
    df['iFVG_Bear'] = False
    if 'FVG_Bear_Top' in df.columns:
        bear_fvg_top = df['FVG_Bear_Top'].ffill()
        df['iFVG_Bull'] = (df['Close'] > bear_fvg_top) & (df['Open'] <= bear_fvg_top)
    if 'FVG_Bull_Bottom' in df.columns:
        bull_fvg_bot = df['FVG_Bull_Bottom'].ffill()
        df['iFVG_Bear'] = (df['Close'] < bull_fvg_bot) & (df['Open'] >= bull_fvg_bot)
    return df

def find_breaker_blocks(df):
    df = df.copy()
    df['Breaker_Bull'] = False
    df['Breaker_Bear'] = False
    if 'Bullish_OB_Price' in df.columns:
        bob = df['Bullish_OB_Price'].ffill()
        df['Breaker_Bear'] = (df['Close'] < bob) & (df['Open'] >= bob)
    if 'Bearish_OB_Price' in df.columns:
        bear_ob = df['Bearish_OB_Price'].ffill()
        df['Breaker_Bull'] = (df['Close'] > bear_ob) & (df['Open'] <= bear_ob)
    return df

def find_liquidity_sweep(df):
    df = df.copy()
    recent_high = df['High'].shift(1).rolling(20).max()
    recent_low = df['Low'].shift(1).rolling(20).min()
    df['Sweep_Bear'] = (df['High'] > recent_high) & (df['Close'] < recent_high)
    df['Sweep_Bull'] = (df['Low'] < recent_low) & (df['Close'] > recent_low)
    return df

def find_ote(df):
    df = df.copy()
    df['OTE_Bull'] = False
    df['OTE_Bear'] = False
    if 'Swing_High' in df.columns and 'Swing_Low' in df.columns:
        sh = df['Swing_High'].ffill()
        sl = df['Swing_Low'].ffill()
        ote_top_bull = sh - (sh - sl) * 0.62
        ote_bot_bull = sh - (sh - sl) * 0.79
        df['OTE_Bull'] = (df['Low'] <= ote_top_bull) & (df['Close'] >= ote_bot_bull)
        
        ote_bot_bear = sl + (sh - sl) * 0.62
        ote_top_bear = sl + (sh - sl) * 0.79
        df['OTE_Bear'] = (df['High'] >= ote_bot_bear) & (df['Close'] <= ote_top_bear)
    return df

def find_asian_range(df):
    df = df.copy()
    asian_mask = (df.index.hour >= 0) & (df.index.hour < 8)
    asian_highs = df[asian_mask].groupby(df[asian_mask].index.date)['High'].max()
    asian_lows = df[asian_mask].groupby(df[asian_mask].index.date)['Low'].min()
    
    dates = df.index.date
    df['ASR_High'] = pd.Series(dates).map(asian_highs).values
    df['ASR_Low'] = pd.Series(dates).map(asian_lows).values
    
    df['ASR_Break_Bull'] = (df['Close'] > df['ASR_High']) & (df['Open'] <= df['ASR_High'])
    df['ASR_Break_Bear'] = (df['Close'] < df['ASR_Low']) & (df['Open'] >= df['ASR_Low'])
    return df

# ============================================================
# TURTLE SOUP — Sahte Kirilim / Stop Hunt Tespiti
# ============================================================
def find_turtle_soup(df, lookback=20):
    """ICT Turtle Soup: Son N mumun high/low'unu gecen ama
    kapanisini o seviye altinda/ustunde yapan mumlar = Sahte kirilim."""
    df = df.copy()
    df['TurtleSoup_Bull'] = False
    df['TurtleSoup_Bear'] = False
    df['TurtleSoup_Level'] = np.nan

    for i in range(lookback + 1, len(df) - 1):
        recent_high = df['High'].iloc[i - lookback:i].max()
        recent_low  = df['Low'].iloc[i - lookback:i].min()
        cur = df.iloc[i]
        nxt = df.iloc[i + 1]

        # BEARISH Turtle Soup: high'i ask ama kapat altinda, sonraki mum duser
        if cur['High'] > recent_high and cur['Close'] < recent_high and nxt['Close'] < cur['Low']:
            df.at[df.index[i], 'TurtleSoup_Bear'] = True
            df.at[df.index[i], 'TurtleSoup_Level'] = recent_high

        # BULLISH Turtle Soup: low'u as ama kapat ustunde, sonraki mum yukselir
        if cur['Low'] < recent_low and cur['Close'] > recent_low and nxt['Close'] > cur['High']:
            df.at[df.index[i], 'TurtleSoup_Bull'] = True
            df.at[df.index[i], 'TurtleSoup_Level'] = recent_low

    return df


# ============================================================
# AMD — Accumulation / Manipulation / Distribution
# ============================================================
def detect_amd_phases(df):
    """Gunluk AMD fazlarini tespit et:
    A=Asya (00-08 UTC), M=Londra (08-10 UTC), D=NY (13-17 UTC).
    Judas Swing: Londra'da ASR kirilimi + NY'da ters yon = gercek yon."""
    df = df.copy()
    df['AMD_Direction'] = None  # 'BULLISH' | 'BEARISH'
    df['AMD_Judas'] = np.nan

    if not hasattr(df.index, 'hour'):
        return df  # timezone yok, atla

    try:
        # UTC'ye normalize et
        idx = df.index
        if idx.tzinfo is None:
            idx_utc = idx
        else:
            idx_utc = idx.tz_convert('UTC')

        asian_mask  = (idx_utc.hour >= 0)  & (idx_utc.hour < 8)
        london_mask = (idx_utc.hour >= 8)  & (idx_utc.hour < 10)

        dates = idx_utc.date
        for date in pd.unique(dates):
            day_mask   = (dates == date)
            a_mask     = day_mask & asian_mask
            l_mask     = day_mask & london_mask

            if not a_mask.any() or not l_mask.any():
                continue

            asian_high = df.loc[a_mask, 'High'].max()
            asian_low  = df.loc[a_mask, 'Low'].min()

            judas      = None
            direction  = None

            for ts, row in df.loc[l_mask].iterrows():
                if row['High'] > asian_high * 1.0005:   # Sahte yukselis
                    judas = row['High']; direction = 'BEARISH'; break
                elif row['Low'] < asian_low * 0.9995:   # Sahte dusus
                    judas = row['Low'];  direction = 'BULLISH'; break

            if judas is None:
                continue

            # Distribution baslangicinda AMD yonunu isle
            ny_mask = day_mask & (idx_utc.hour >= 13) & (idx_utc.hour < 17)
            if ny_mask.any():
                df.loc[ny_mask, 'AMD_Direction'] = direction
                df.loc[ny_mask, 'AMD_Judas']     = judas
    except Exception:
        pass

    # Kolay erisim icin bool sutunlari
    df['AMD_Bull'] = df['AMD_Direction'] == 'BULLISH'
    df['AMD_Bear'] = df['AMD_Direction'] == 'BEARISH'
    return df


# ============================================================
# IPDA — Interbank Price Delivery Algorithm Levels
# ============================================================
def find_ipda_levels(df_daily):
    """20/40/60 gunluk high/low seviyeleri (IPDA hedef bolgeler).
    Gunluk veriye uygulanir; yakin seviye %0.3 icindeyse bonus skor doner."""
    if df_daily is None or len(df_daily) < 20:
        return None

    current_price = float(df_daily['Close'].iloc[-1])
    levels = {}

    for period in [20, 40, 60]:
        if len(df_daily) >= period:
            levels[f'{period}d_high'] = float(df_daily['High'].tail(period).max())
            levels[f'{period}d_low']  = float(df_daily['Low'].tail(period).min())

    if not levels:
        return None

    nearest_name, nearest_price, nearest_dist = None, None, float('inf')
    for name, price in levels.items():
        dist = abs(current_price - price) / current_price
        if dist < nearest_dist:
            nearest_dist  = dist
            nearest_name  = name
            nearest_price = price

    if nearest_dist < 0.003:   # %0.3 icinde
        return {
            'level':        nearest_name,
            'price':        nearest_price,
            'distance_pct': nearest_dist * 100,
            'score':        25,
            'all_levels':   levels
        }
    return None


# ============================================================
# SMT — Smart Money Divergence (Korelasyon Ayrisimi)
# ============================================================
def find_smt_divergence(df1, df2, ticker1='Asset1', ticker2='Asset2', lookback=10):
    """Iki korelasyonlu varligin birbirinden ayrilmasi = kurumsal sinyal.
    SPY yeni high yaptiysa ama QQQ yapmadiysa => BEARISH SMT."""
    if df1 is None or df2 is None or len(df1) < lookback or len(df2) < lookback:
        return None

    high1 = float(df1['High'].tail(lookback).max())
    high2 = float(df2['High'].tail(lookback).max())
    low1  = float(df1['Low'].tail(lookback).min())
    low2  = float(df2['Low'].tail(lookback).min())
    cur1  = float(df1['Close'].iloc[-1])
    cur2  = float(df2['Close'].iloc[-1])

    # BEARISH SMT: df1 yeni high, df2 yapmadi
    if cur1 >= high1 and (high2 - cur2) / high2 > 0.002:
        return {
            'type':      'SMT_BEARISH',
            'ticker1':   ticker1,
            'ticker2':   ticker2,
            'direction': 'BEARISH',
            'score':     30
        }

    # BULLISH SMT: df1 yeni low, df2 yapmadi
    if cur1 <= low1 and (cur2 - low2) / low2 > 0.002:
        return {
            'type':      'SMT_BULLISH',
            'ticker1':   ticker1,
            'ticker2':   ticker2,
            'direction': 'BULLISH',
            'score':     30
        }

    return None

def check_fvg_overlap(df, cur_idx, ob_high, ob_low):
    try:
        for idx in range(cur_idx - 5, cur_idx + 1):
            if idx < 2: continue
            prev_high = df.iloc[idx-2]['High']
            next_low = df.iloc[idx]['Low']
            prev_low = df.iloc[idx-2]['Low']
            next_high = df.iloc[idx]['High']
            if next_low > prev_high:
                if max(ob_low, prev_high) <= min(ob_high, next_low): return True
            if next_high < prev_low:
                if max(ob_low, next_high) <= min(ob_high, prev_low): return True
    except: pass
    return False

def detect_amd_phases_v2(df):
    df_est = df.copy()
    if df_est.index.tz is None:
        df_est.index = df_est.index.tz_localize('UTC')
    df_est.index = df_est.index.tz_convert('America/New_York')
    today = df_est.index[-1].date()
    
    acc_data = df_est.between_time('19:00', '01:00')
    acc_data_today = acc_data[acc_data.index.date == today]
    if len(acc_data_today) < 3: return None
    
    acc_body_high = acc_data_today[['Open','Close']].max(axis=1).max()
    acc_body_low = acc_data_today[['Open','Close']].min(axis=1).min()
    acc_range = acc_body_high - acc_body_low
    
    atr = calculate_adx(df_est, 14)  # Approximate using calculate_adx length, or we can just use a simple ATR calc
    # To be safe, let's calculate a quick simple ATR 14
    tr = pd.concat([df_est['High'] - df_est['Low'], 
                    (df_est['High'] - df_est['Close'].shift()).abs(), 
                    (df_est['Low'] - df_est['Close'].shift()).abs()], axis=1).max(axis=1)
    atr_val = tr.rolling(14).mean().iloc[-1]
    
    if acc_range > atr_val * 0.5: return None
    
    manip_data = df_est.between_time('01:00', '07:00')
    manip_data_today = manip_data[manip_data.index.date == today]
    if len(manip_data_today) < 2: return None
    
    judas_direction = None
    judas_candle = None
    avg_vol = manip_data_today['Volume'].mean() if 'Volume' in manip_data_today.columns else 0
    
    for idx, row in manip_data_today.iterrows():
        body_high = max(row['Open'], row['Close'])
        body_low = min(row['Open'], row['Close'])
        vol = row['Volume'] if 'Volume' in row else 0
        if body_high > acc_body_high:
            if vol > avg_vol * 1.3 or avg_vol == 0:
                judas_direction = 'BEARISH_JUDAS'
                judas_candle = row
                break
        elif body_low < acc_body_low:
            if vol > avg_vol * 1.3 or avg_vol == 0:
                judas_direction = 'BULLISH_JUDAS'
                judas_candle = row
                break
                
    if not judas_direction: return None
    
    dist_data = df_est.between_time('07:00', '13:00')
    dist_data_today = dist_data[dist_data.index.date == today]
    real_direction = 'LONG' if judas_direction == 'BULLISH_JUDAS' else 'SHORT'
    
    # Fonsiyonlar geriye DataFrame donuyor, bunlari dicte cevirelim veya basitce kontrol edelim
    fvg_df = find_fvg(dist_data_today)
    ob_df = find_order_blocks(dist_data_today)
    
    entry_price = None
    confirmation = 'NONE'
    
    if 'FVG_Bull_Top' in fvg_df.columns and fvg_df['FVG_Bull'].any() and real_direction == 'LONG':
        last_fvg = fvg_df[fvg_df['FVG_Bull']].iloc[-1]
        entry_price = (last_fvg['FVG_Bull_Top'] + last_fvg['FVG_Bull_Bottom']) / 2
        confirmation = 'FVG'
    elif 'Bullish_OB_Price' in ob_df.columns and ob_df['Bullish_OB_Price'].notna().any() and real_direction == 'LONG':
        entry_price = ob_df['Bullish_OB_Price'].dropna().iloc[-1]
        confirmation = 'OB'
        
    if 'FVG_Bear_Bottom' in fvg_df.columns and fvg_df['FVG_Bear'].any() and real_direction == 'SHORT':
        last_fvg = fvg_df[fvg_df['FVG_Bear']].iloc[-1]
        entry_price = (last_fvg['FVG_Bear_Top'] + last_fvg['FVG_Bear_Bottom']) / 2
        confirmation = 'FVG'
    elif 'Bearish_OB_Price' in ob_df.columns and ob_df['Bearish_OB_Price'].notna().any() and real_direction == 'SHORT':
        entry_price = ob_df['Bearish_OB_Price'].dropna().iloc[-1]
        confirmation = 'OB'
        
    return {
        'phase': 'DISTRIBUTION',
        'direction': real_direction,
        'judas': judas_direction,
        'acc_high': acc_body_high,
        'acc_low': acc_body_low,
        'entry': entry_price,
        'sl': judas_candle['Low'] if real_direction == 'LONG' else judas_candle['High'],
        'score': 85,
        'confirmation': confirmation
    }

def find_turtle_soup_v2(df, lookback=20):
    signals = []
    for i in range(lookback+2, len(df)-2):
        window = df.iloc[i-lookback:i]
        current = df.iloc[i]
        prev = df.iloc[i-1]
        
        highs = window['High'].values
        for j in range(len(highs)-1):
            for k in range(j+1, len(highs)):
                if abs(highs[j] - highs[k]) / highs[j] < 0.0005:
                    equal_high = max(highs[j], highs[k])
                    if current['High'] > equal_high:
                        next_c = df.iloc[i+1]
                        choch = next_c['Close'] < current['Low']
                        fvg_formed = (current['Low'] > prev['High'])
                        if choch or fvg_formed:
                            signals.append({
                                'type': 'EQH_TURTLE_SOUP',
                                'direction': 'SHORT',
                                'swept_level': equal_high,
                                'entry': current['Low'],
                                'sl': current['High'] * 1.001,
                                'score': 95,
                                'index': i
                            })
                            
        lows = window['Low'].values
        for j in range(len(lows)-1):
            for k in range(j+1, len(lows)):
                if abs(lows[j] - lows[k]) / lows[j] < 0.0005:
                    equal_low = min(lows[j], lows[k])
                    if current['Low'] < equal_low:
                        next_c = df.iloc[i+1]
                        choch = next_c['Close'] > current['High']
                        fvg_formed = (current['High'] < prev['Low'])
                        if choch or fvg_formed:
                            signals.append({
                                'type': 'EQL_TURTLE_SOUP',
                                'direction': 'LONG',
                                'swept_level': equal_low,
                                'entry': current['High'],
                                'sl': current['Low'] * 0.999,
                                'score': 95,
                                'index': i
                            })
    return signals

def find_ipda_v2(df_daily, df_signal):
    if df_daily is None or df_signal is None or df_daily.empty or df_signal.empty:
        return None
    levels = {}
    current = df_signal['Close'].iloc[-1]
    
    for period in [20, 40, 60]:
        if len(df_daily) >= period:
            period_data = df_daily.tail(period)
            high = period_data['High'].max()
            low = period_data['Low'].min()
            levels[f'{period}d'] = {'high': high, 'low': low}
            
    ipda_signals = []
    for period_name, lvl in levels.items():
        low_distance = (current - lvl['low']) / lvl['low']
        high_distance = (lvl['high'] - current) / lvl['high']
        
        if 0 < low_distance < 0.005:
            recent_low = df_signal['Low'].tail(5).min()
            if recent_low < lvl['low'] and current > lvl['low']:
                ipda_signals.append({
                    'type': f'IPDA_OFFSET_ACC_{period_name}',
                    'direction': 'LONG',
                    'level': lvl['low'],
                    'score': 35,
                    'model': 'offset_accumulation'
                })
                
        if 0 < high_distance < 0.005:
            recent_high = df_signal['High'].tail(5).max()
            if recent_high > lvl['high'] and current < lvl['high']:
                ipda_signals.append({
                    'type': f'IPDA_OFFSET_DIST_{period_name}',
                    'direction': 'SHORT',
                    'level': lvl['high'],
                    'score': 35,
                    'model': 'offset_distribution'
                })
                
    if ipda_signals:
        return max(ipda_signals, key=lambda x: x['score'])
    return None

def find_order_blocks_v2(df, lookback=50):
    obs = []
    
    tr = pd.concat([df['High'] - df['Low'], 
                    (df['High'] - df['Close'].shift()).abs(), 
                    (df['Low'] - df['Close'].shift()).abs()], axis=1).max(axis=1)
    df_atr = tr.rolling(14).mean()
    
    for i in range(3, min(lookback, len(df)-3)):
        atr = df_atr.iloc[max(0, i-14):i].mean()
        if pd.isna(atr): continue
        
        candle_range = df.iloc[i]['High'] - df.iloc[i]['Low']
        if candle_range < atr * 1.5: continue
        
        if df.iloc[i]['Close'] > df.iloc[i]['Open']:
            for j in range(i-1, max(0, i-5), -1):
                if df.iloc[j]['Close'] < df.iloc[j]['Open']:
                    ob_high = df.iloc[j]['High']
                    ob_low = df.iloc[j]['Low']
                    ob_body_high = max(df.iloc[j]['Open'], df.iloc[j]['Close'])
                    ob_body_low = min(df.iloc[j]['Open'], df.iloc[j]['Close'])
                    
                    fvg_overlap = check_fvg_overlap(df, i, ob_high, ob_low)
                    
                    obs.append({
                        'type': 'BULLISH_OB',
                        'high': ob_high,
                        'low': ob_low,
                        'body_high': ob_body_high,
                        'body_low': ob_body_low,
                        'index': j,
                        'candle_index': i,
                        'fvg_overlap': fvg_overlap,
                        'score': 25 if not fvg_overlap else 40,
                        'mitigated': False
                    })
                    break
                    
        elif df.iloc[i]['Close'] < df.iloc[i]['Open']:
            for j in range(i-1, max(0, i-5), -1):
                if df.iloc[j]['Close'] > df.iloc[j]['Open']:
                    ob_high = df.iloc[j]['High']
                    ob_low = df.iloc[j]['Low']
                    ob_body_high = max(df.iloc[j]['Open'], df.iloc[j]['Close'])
                    ob_body_low = min(df.iloc[j]['Open'], df.iloc[j]['Close'])
                    
                    fvg_overlap = check_fvg_overlap(df, i, ob_high, ob_low)
                    
                    obs.append({
                        'type': 'BEARISH_OB',
                        'high': ob_high,
                        'low': ob_low,
                        'body_high': ob_body_high,
                        'body_low': ob_body_low,
                        'index': j,
                        'candle_index': i,
                        'fvg_overlap': fvg_overlap,
                        'score': 25 if not fvg_overlap else 40,
                        'mitigated': False
                    })
                    break
                    
    current_price = df['Close'].iloc[-1]
    active_obs = []
    for ob in obs:
        if ob['type'] == 'BULLISH_OB':
            if current_price > ob['low']:
                active_obs.append(ob)
        else:
            if current_price < ob['high']:
                active_obs.append(ob)
                
    return active_obs

def calculate_signal_score(
    bias, bos, ote, asr, ifvg, breaker, kill_zone,
    direction='BULLISH',
    turtle_soup_v2=None, amd_v2=None, ipda_v2=None, smt_v2=None, active_ob_v2=None, current_fvg=None
):
    score = 0
    reasons = []
    
    if bias == direction:
        score += 20; reasons.append('Trend Uyumu')
    if bos:
        score += 15; reasons.append('BOS/CHoCH')
    if ote:
        score += 10; reasons.append('OTE Zone')
    if asr:
        score += 10; reasons.append('ASR Kirilimi')
    if ifvg:
        score += 10; reasons.append('iFVG Reversal')
    if breaker:
        score += 10; reasons.append('Breaker Block')
    if kill_zone:
        score += 15; reasons.append('Kill Zone')
        
    if current_fvg:
        score += 15; reasons.append('FVG')
        
    if active_ob_v2:
        score += active_ob_v2['score']
        reasons.append(f"OB ({'FVG Overlap' if active_ob_v2['fvg_overlap'] else 'Normal'})")
        
    if turtle_soup_v2:
        score += turtle_soup_v2['score']
        reasons.append(f"TURTLE SOUP ({turtle_soup_v2['type']})")
        
    if amd_v2:
        score += amd_v2['score']
        reasons.append('AMD Setup')
        
    if ipda_v2:
        score += ipda_v2['score']
        reasons.append(f"IPDA Level ({ipda_v2['type']})")
        
    if smt_v2:
        score += smt_v2['score']
        reasons.append('SMT Div')
        
    if score >= 90:
        position_size = 0.015
    elif score >= 70:
        position_size = 0.01
    elif score >= 50:
        position_size = 0.005
    else:
        position_size = 0.0
        
    return score, reasons, position_size
