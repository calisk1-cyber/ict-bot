import pandas as pd
import numpy as np
import pandas_ta as ta
from datetime import datetime, timedelta
import pytz
import yfinance as yf

# --- TIME & SESSION FILTERS ---

def is_silver_bullet_zone(ts):
    """ICT Silver Bullet Time Windows (UTC for EURUSD/Majors)"""
    h = ts.hour
    if h == 7: return True   # London Open (07:00-08:00 UTC)
    if h == 14: return True  # NY AM (14:00-15:00 UTC)
    if h == 18: return True  # NY PM (18:00-19:00 UTC)
    return False

def is_macro_time(ts):
    """ICT Macro Windows - Algorithmic Liquidity Injections"""
    h, m = ts.hour, ts.minute
    if h == 7 and m >= 50: return True
    if h == 8 and m <= 10: return True
    if h == 13 and 10 <= m <= 40: return True
    if h == 14 and m >= 50: return True
    if h == 15 and m <= 10: return True
    return False

# --- CORE SMC & ICT INDICATORS ---

def find_fvg_v3(df):
    """Fair Value Gap with Displacement Check"""
    df = df.copy()
    # middle candle body size vs avg
    tr = (df['High'] - df['Low']).rolling(14).mean()
    middle_body = (df['Close'].shift(1) - df['Open'].shift(1)).abs()
    is_displacement = middle_body > (tr * 1.2)
    
    df['FVG_Bull'] = (df['Low'] > df['High'].shift(2)) & is_displacement
    df['FVG_Bear'] = (df['High'] < df['Low'].shift(2)) & is_displacement
    return df

def find_ifvg(df):
    """Inversion FVG (IFVG) - Broken gaps becoming support/resistance"""
    df = df.copy()
    df['IFVG_Bull'] = False
    df['IFVG_Bear'] = False
    # logic: price closing above a bearish FVG top or below a bullish FVG bottom
    for i in range(5, len(df)):
        # Very simplified check for backtest/live sync
        if df['Close'].iloc[i] > df['High'].iloc[i-2] and df['High'].iloc[i-2] > df['Low'].iloc[i]:
            df.loc[df.index[i], 'IFVG_Bull'] = True
    return df

def find_turtle_soup(df, lookback=20):
    """Liquidity Sweep Detection (External Range Liquidity)"""
    df = df.copy()
    high_level = df['High'].shift(1).rolling(lookback).max()
    low_level = df['Low'].shift(1).rolling(lookback).min()
    df['TurtleSoup_Bull'] = (df['Low'] < low_level) & (df['Close'] > low_level)
    df['TurtleSoup_Bear'] = (df['High'] > high_level) & (df['Close'] < high_level)
    return df

def find_inducement(df, lookback=10):
    """Liquidity Inducement (IDM) - Internal structure trap"""
    df = df.copy()
    df['IDM_Bull'] = False
    df['IDM_Bear'] = False
    for i in range(lookback, len(df)):
        low_sweep = df['Low'].iloc[i] < df['Low'].iloc[i-lookback:i].min()
        if low_sweep and df['Close'].iloc[i] > df['Low'].iloc[i-lookback:i].min():
            df.loc[df.index[i], 'IDM_Bull'] = True
    return df

def find_smt_proxy(df_main, df_corr):
    """SMT Divergence Proxy"""
    df_main = df_main.copy()
    df_main['SMT_Bull'] = False
    common_idx = df_main.index.intersection(df_corr.index)
    for i in range(20, len(common_idx)):
        idx = common_idx[i]
        prev_idx = common_idx[i-20:i]
        if df_main.loc[idx, 'Low'] < df_main.loc[prev_idx, 'Low'].min():
            if df_corr.loc[idx, 'Low'] > df_corr.loc[prev_idx, 'Low'].min():
                df_main.loc[idx, 'SMT_Bull'] = True
    return df_main

# --- UTILS ---

def download_full_history(ticker, interval='5m', period='3d'):
    try:
        t = ticker.replace("_", "") + "=X"
        data = yf.download(t, period=period, interval=interval, progress=False)
        if data.empty: return pd.DataFrame()
        data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]
        return data
    except: return pd.DataFrame()
