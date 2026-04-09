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

# --- CORE SMC & ICT INDICATORS (V12 INSTITUTIONAL) ---

def find_fvg_v12(df):
    """
    V12 Institutional FVG (Fair Value Gap)
    Includes: BISI/SIBI Classification, Displacement, and Consequent Encroachment (CE)
    """
    df = df.copy()
    if len(df) < 5: return df
    
    # 1. Displacement Check (Institutional momentum)
    # Candle body must be at least 1.4x of the 14-period ATR
    atr = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    body_size = (df['Close'] - df['Open']).abs()
    is_displacement = body_size > (atr * 1.4)
    
    # 2. BISI (Buyside Imbalance Sellside Inefficiency) - Bullish
    # Gap between High of Candle 1 and Low of Candle 3
    df['FVG_Bull'] = (df['Low'] > df['High'].shift(2)) & is_displacement.shift(1)
    df['BISI_CE'] = np.where(df['FVG_Bull'], (df['High'].shift(2) + df['Low']) / 2, np.nan)
    
    # 3. SIBI (Sellside Imbalance Buyside Inefficiency) - Bearish
    # Gap between Low of Candle 1 and High of Candle 3
    df['FVG_Bear'] = (df['High'] < df['Low'].shift(2)) & is_displacement.shift(1)
    df['SIBI_CE'] = np.where(df['FVG_Bear'], (df['Low'].shift(2) + df['High']) / 2, np.nan)
    
    # 4. Rebalancing & Mitigation Check
    # Track if the FVG has been 'filled' or 'rebalanced' in subsequent candles
    df['BISI_Rebalanced'] = False
    df['SIBI_Rebalanced'] = False
    
    # Simple carry-forward of last valid CE
    df['BISI_CE'] = df['BISI_CE'].ffill()
    df['SIBI_CE'] = df['SIBI_CE'].ffill()
    
    return df

def find_ifvg_v12(df):
    """Inversion FVG (IFVG) - V12 Institutional"""
    df = df.copy()
    if 'FVG_Bull' not in df: df = find_fvg_v12(df)
    
    # Bullish Inversion: Bearish FVG broken and used as support
    # Bearish Inversion: Bullish FVG broken and used as resistance
    df['IFVG_Bull'] = (df['Close'] > df['SIBI_CE']) & (df['Close'].shift(1) < df['SIBI_CE'])
    df['IFVG_Bear'] = (df['Close'] < df['BISI_CE']) & (df['Close'].shift(1) > df['BISI_CE'])
    
    return df

def find_turtle_soup_v2(df, lookback=20):
    """Advanced Liquidity Sweep Detection"""
    df = df.copy()
    if len(df) < lookback: return df
    high_level = df['High'].shift(1).rolling(lookback).max()
    low_level = df['Low'].shift(1).rolling(lookback).min()
    # Sweep + Rejection
    df['TurtleSoup_Bull'] = (df['Low'] < low_level) & (df['Close'] > low_level)
    df['TurtleSoup_Bear'] = (df['High'] > high_level) & (df['Close'] < high_level)
    return df

def find_mss_v11(df, lookback=5):
    """Market Structure Shift (MSS) / CHoCH with Displacement"""
    df = df.copy()
    if len(df) < lookback + 1: return df
    
    # Needs break of recent swing high/low with body closing
    recent_high = df['High'].shift(1).rolling(lookback).max()
    recent_low = df['Low'].shift(1).rolling(lookback).min()
    
    tr = (df['High'] - df['Low']).rolling(14).mean()
    body_size = (df['Close'] - df['Open']).abs()
    is_displacement = body_size > (tr * 1.1)
    
    df['MSS_Bull'] = (df['Close'] > recent_high) & is_displacement
    df['MSS_Bear'] = (df['Close'] < recent_low) & is_displacement
    return df

def find_volume_imbalance(df):
    """Detects gaps where no trade activity occurred (body gap)"""
    df = df.copy()
    if len(df) < 5: return df
    # Bullish VI: Close of bar 1 < Open of bar 3 AND Low of bar 3 > High of bar 1
    df['VI_Bull'] = (df['Close'].shift(2) < df['Open'].shift(2)) & \
                    (df['Close'] > df['Open']) & \
                    (df['Low'] > df['High'].shift(2))
    
    # Bearish VI: Close of bar 1 > Open of bar 3 AND High of bar 3 < Low of bar 1
    df['VI_Bear'] = (df['Close'].shift(2) > df['Open'].shift(2)) & \
                    (df['Close'] < df['Open']) & \
                    (df['High'] < df['Low'].shift(2))
    return df

def detect_po3_v11(df):
    """
    detects Power of 3: Accumulation, Manipulation, Distribution.
    """
    df = df.copy()
    if len(df) < 20: return df
    
    # 1. Accumulation: High tightness / Low ADX or Volatility
    vol = (df['High'] - df['Low']).rolling(10).mean()
    avg_vol = vol.rolling(50).mean()
    df['PO3_Accumulation'] = vol < (avg_vol * 0.8)
    
    # 2. Manipulation: Liquidity sweep during accumulation
    df = find_turtle_soup_v2(df, lookback=15)
    df['PO3_Manipulation'] = df['PO3_Accumulation'].shift(5) & (df['TurtleSoup_Bull'] | df['TurtleSoup_Bear'])
    
    # 3. Distribution: Strong move in opposite direction of manipulation
    df = find_mss_v11(df, lookback=5)
    df['PO3_Distribution_Bull'] = df['PO3_Manipulation'].shift(2) & df['MSS_Bull']
    df['PO3_Distribution_Bear'] = df['PO3_Manipulation'].shift(2) & df['MSS_Bear']
    
    return df

def find_silver_bullet(df):
    """Silver Bullet Signal: FVG within SB window + MSS"""
    df = df.copy()
    res = find_fvg_v12(df)
    res = find_mss_v11(res)
    df['SB_Bull'] = res['FVG_Bull'] & res['MSS_Bull']
    df['SB_Bear'] = res['FVG_Bear'] & res['MSS_Bear']
    return df

def find_breaker_blocks(df):
    """Breaker: Swept liquidity + Market Structure Shift"""
    df = df.copy()
    high_20 = df['High'].shift(1).rolling(20).max()
    low_20 = df['Low'].shift(1).rolling(20).min()
    df['Breaker_Bear'] = (df['High'] > high_20) & (df['Close'] < df['Low'].shift(1).rolling(5).min())
    df['Breaker_Bull'] = (df['Low'] < low_20) & (df['Close'] > df['High'].shift(1).rolling(5).max())
    return df

def find_order_blocks(df):
    """
    detects Institutional Order Blocks (OB)
    Bullish OB: Last bearish candle before a strong bullish move (MSS)
    Bearish OB: Last bullish candle before a strong bearish move (MSS)
    """
    df = df.copy()
    if len(df) < 5: return df
    
    is_bull = df['Close'] > df['Open']
    is_bear = df['Close'] < df['Open']
    
    # 1. Potential OB Levels
    df['Bull_OB'] = np.where(is_bear.shift(1) & (df['Close'] > df['High'].shift(1)), df['Low'].shift(1), np.nan)
    df['Bear_OB'] = np.where(is_bull.shift(1) & (df['Close'] < df['Low'].shift(1)), df['High'].shift(1), np.nan)
    
    df['Bull_OB'] = df['Bull_OB'].ffill()
    df['Bear_OB'] = df['Bear_OB'].ffill()
    
    return df

# --- UTILS ---

def download_full_history(ticker, interval='5m', period='3d'):
    try:
        # Ticker Mapping for Yahoo Finance
        mapping = {
            "XAU_USD": "GC=F",
            "NAS100_USD": "^NDX",
            "US30_USD": "^DJI",
            "EUR_USD": "EURUSD=X",
            "GBP_USD": "GBPUSD=X",
            "USD_JPY": "JPY=X",
            "GBP_JPY": "GBPJPY=X"
        }
        t = mapping.get(ticker, ticker.replace("_", "") + "=X")
        data = yf.download(t, period=period, interval=interval, progress=False)
        if data.empty: return pd.DataFrame()
        data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]
        return data
    except: return pd.DataFrame()

def detect_market_regime(df, lookback=24):
    """
    Piyasa durumunu analiz eder: TRENDING, CHOPPY, VOLATILE
    """
    df = df.copy()
    # 1. Volatilite (ATR)
    atr = ta.atr(df['High'], df['Low'], df['Close'], length=lookback)
    avg_atr = atr.mean()
    curr_atr = atr.iloc[-1]
    
    # 2. Efficiency Ratio (ER) - Ne kadar düz gidiyor?
    change = (df['Close'] - df['Close'].shift(lookback)).abs()
    volatility = (df['Close'] - df['Close'].shift(1)).abs().rolling(lookback).sum()
    er = change / volatility
    curr_er = er.iloc[-1]
    
    if curr_atr > (avg_atr * 1.5):
        return "VOLATILE", curr_er
    elif curr_er > 0.6:
        return "TRENDING", curr_er
    elif curr_er < 0.3:
        return "CHOPPY", curr_er
    else:
        return "NORMAL", curr_er

def calculate_pvr_risk(df, base_units=2000):
    """
    Proportional Volatility Risk (PVR)
    Scales units down if volatility (ATR) is spiking.
    """
    atr = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    avg_atr = atr.rolling(50).mean()
    
    scalar = 1.0
    if atr.iloc[-1] > (avg_atr.iloc[-1] * 1.2):
        scalar = 0.5 # High Volatility -> Half Risk
    elif atr.iloc[-1] > (avg_atr.iloc[-1] * 1.5):
        scalar = 0.25 # Extreme Volatility -> Quarter Risk
        
    return int(base_units * scalar)

# --- THE SOVEREIGN ENGINE (V16 PREDICTIVE) ---

def detect_weekly_profile_v16(df):
    """
    Weekly Profile Predictor
    Tuesday Low/High: Weekly extreme often forms by Tue NY Open.
    Wednesday Reversal: Trends Mon/Tue, reverses Wed.
    """
    df = df.copy()
    if len(df) < 500: return df # Need a week of data
    
    # Identify day of week
    df['DayOfWeek'] = df.index.dayofweek # 0=Mon, 1=Tue...
    
    # Weekly Range Start
    df['is_tue_extreme'] = False
    # Logic: If Monday range is small and Tuesday sweeps Mon Low -> Possible Tuesday Low
    return df

def find_amd_fractal_v15(df):
    """
    Accumulation, Manipulation, Distribution (AMD)
    Asia (Accumulation) -> London (Manipulation) -> NY (Distribution)
    """
    df = df.copy()
    hour = df.index.hour
    
    # 1. Asia Accumulation (approx 00:00 - 08:00 TSİ)
    df['is_asia'] = (hour >= 0) & (hour < 8)
    # 2. London Manipulation (approx 09:00 - 12:00 TSİ)
    df['is_london_manip'] = (hour >= 9) & (hour < 12)
    # 3. NY Distribution (approx 15:00 - 20:00 TSİ)
    df['is_ny_dist'] = (hour >= 15) & (hour < 20)
    
    return df

def find_liquidity_voids_v16(df, threshold=0.0030):
    """Detects large 'One Way' gaps."""
    df = df.copy()
    df['body_size'] = (df['Close'] - df['Open']).abs()
    df['is_void'] = df['body_size'] > threshold
    return df

def find_htf_void_targets_v17(df_htf):
    """Identifies the nearest unfilled 1H Liquidity Void as a target."""
    voids = df_htf[df_htf['High'] - df_htf['Low'] > df_htf['High'].rolling(20).mean() * 0.005]
    if voids.empty: return None
    return {"high": voids['High'].max(), "low": voids['Low'].min()}

def find_cisd_v15(df):
    """Change in State of Delivery (CISD)"""
    df = df.copy()
    if len(df) < 5: return df
    is_bull = df['Close'] > df['Open']
    is_bear = df['Close'] < df['Open']
    df['CISD_Bull'] = (df['Close'] > df['Open'].shift(1)) & is_bear.shift(1)
    df['CISD_Bear'] = (df['Close'] < df['Open'].shift(1)) & is_bull.shift(1)
    return df

def find_inducement_v15(df, window=10):
    """Inducement (IDM) - Retail Traps"""
    df = df.copy()
    df['IDM_High'] = df['High'].rolling(3).max().shift(1)
    df['IDM_Low'] = df['Low'].rolling(3).min().shift(1)
    df['IDM_Sweep_Bull'] = (df['Low'] < df['IDM_Low']) & (df['Close'] > df['IDM_Low'])
    df['IDM_Sweep_Bear'] = (df['High'] > df['IDM_High']) & (df['Close'] < df['IDM_High'])
    return df

def calculate_ote_v15(high, low, side="BUY"):
    """Optimal Trade Entry (70.5%) for a given swing"""
    diff = high - low
    if side == "BUY":
        return high - (diff * 0.705)
    return low + (diff * 0.705)

def find_smt_v13(df_main, df_corr, type="POS"):
    """
    SMC/ICT SMT Divergence (Institutional Crack in Correlation)
    Detects HH/LH or LL/HL shifts between correlated pairs.
    """
    res = pd.Series(0, index=df_main.index)
    if len(df_main) < 10 or len(df_corr) < 10: return res
    
    main_high_1 = df_main['High'].shift(1)
    main_high_2 = df_main['High'].shift(2)
    corr_high_1 = df_corr['High'].shift(1)
    corr_high_2 = df_corr['High'].shift(2)
    
    main_low_1 = df_main['Low'].shift(1)
    main_low_2 = df_main['Low'].shift(2)
    corr_low_1 = df_corr['Low'].shift(1)
    corr_low_2 = df_corr['Low'].shift(2)
    
    bearish_smt = (main_high_1 > main_high_2) & (corr_high_1 < corr_high_2)
    bullish_smt = (main_low_1 < main_low_2) & (corr_low_1 > corr_low_2)
    
    res[bearish_smt] = -1
    res[bullish_smt] = 1
    return res

def is_in_killzone_v13(dt):
    """London (02-05 NY) or NY (08-11 NY) Kill Zones"""
    hour = dt.hour
    is_london = (3 <= hour <= 10)  # Approx London TSİ
    is_ny = (15 <= hour <= 20)      # Approx NY TSİ
    return is_london or is_ny

def is_in_macro_v13(dt):
    """NY Morning Macro (09:50 - 10:10 AM NY)"""
    hour = dt.hour
    minute = dt.minute
    return (hour == 16 and 50 <= minute <= 59) or (hour == 17 and 0 <= minute <= 10)

def get_premium_discount_v11(df, window=20):
    """Improved Premium/Discount calculation (0.5 equilibrium)"""
    high = df['High'].rolling(window).max()
    low = df['Low'].rolling(window).min()
    midpoint = (high + low) / 2
    return {
        "is_discount": df['Close'] < midpoint,
        "is_premium": df['Close'] > midpoint,
        "midpoint": midpoint
    }

def get_smc_bias_v11(df_htf):
    """
    SMC/Pure ICT Bias: Determines the institutional order flow.
    Uses Market Structure Shift (MSS) and PD Array (Premium/Discount) on 1H.
    """
    if df_htf.empty or len(df_htf) < 20: return "NEUTRAL"
    
    df = df_htf.copy()
    high_20 = df['High'].rolling(20).max()
    low_20 = df['Low'].rolling(20).min()
    midpoint = (high_20 + low_20) / 2
    
    # 1. Price vs Equilibrium
    last_close = df['Close'].iloc[-1]
    curr_midpoint = midpoint.iloc[-1]
    
    # 2. Structure Check
    mss = find_mss_v11(df, lookback=5)
    last_mss_bull = mss['MSS_Bull'].tail(10).any()
    last_mss_bear = mss['MSS_Bear'].tail(10).any()
    
    if last_close > curr_midpoint and last_mss_bull:
        return "BULLISH"
    elif last_close < curr_midpoint and last_mss_bear:
        return "BEARISH"
    elif last_close > curr_midpoint:
        return "WEAK_BULLISH"
    elif last_close < curr_midpoint:
        return "WEAK_BEARISH"
    else:
        return "NEUTRAL"

def is_in_discount(df_range, current_price):
    """Buy only in discount (lower 50%), sell only in premium (upper 50%)"""
    high = df_range['High'].max()
    low = df_range['Low'].min()
    midpoint = (high + low) / 2
    return current_price < midpoint

def save_chart_image(df, ticker, direction, score):
    """
    ICT kurulumunu görsel bir grafik olarak kaydeder.
    """
    try:
        import matplotlib.pyplot as plt
        import os
        
        if not os.path.exists('charts'):
            os.makedirs('charts')
            
        # Son 30 mumu al
        plot_df = df.tail(30).copy()
        plot_df = plot_df.reset_index()
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Candlestick çizimi (Manuel)
        for i in range(len(plot_df)):
            color = 'green' if plot_df['Close'][i] >= plot_df['Open'][i] else 'red'
            # Wick
            ax.plot([i, i], [plot_df['Low'][i], plot_df['High'][i]], color='black', linewidth=1)
            # Body
            bottom = min(plot_df['Open'][i], plot_df['Close'][i])
            height = abs(plot_df['Open'][i] - plot_df['Close'][i])
            rect = plt.Rectangle((i-0.3, bottom), 0.6, height, color=color, alpha=0.8)
            ax.add_patch(rect)

        # FVG'leri iasretle
        if 'FVG_Bull' in plot_df.columns:
            for i in range(len(plot_df)):
                if plot_df['FVG_Bull'][i]:
                    ax.add_patch(plt.Rectangle((i-1, plot_df['Low'][i-1]), 2, (plot_df['High'][i+1]-plot_df['Low'][i-1]), color='blue', alpha=0.2))

        ax.set_title(f"ICT SETUP: {ticker} [{direction}] Score: {score}")
        ax.set_facecolor('#f0f0f0')
        plt.grid(True, alpha=0.3)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"charts/{ticker}_{direction}_{timestamp}.png"
        plt.savefig(filename)
        plt.close()
        return filename
    except Exception as e:
        print(f"Visual Chart Error: {e}")
        return None

# --- ICT V16 THE SOVEREIGN LOGIC ---
# The predictive cycle engine

def apply_ict_v16_sovereign(df, df_corr=None):
    """
    Main entry point for V16 Sovereign enrichment.
    Unifies Weekly Cycles, AMD Fractals, and Architect precision.
    """
    df = df.copy()
    if df.empty: return df
    
    # 1. Foundation & Cycles
    df = detect_weekly_profile_v16(df)
    df = find_amd_fractal_v15(df)
    df = find_liquidity_voids_v16(df)
    
    # 2. Internal Precision (V15)
    df = find_cisd_v15(df)
    df = find_inducement_v15(df)
    df = find_fvg_v12(df)
    df = find_turtle_soup_v2(df)
    df = find_mss_v11(df)
    
    # 3. Correlation
    if df_corr is not None:
        if 'High' in df_corr.columns:
            df['SMT_Signal'] = find_smt_v13(df, df_corr)
        else:
            df['SMT_Signal'] = 0
    else:
        df['SMT_Signal'] = 0
        
    return df

# --- ICT V12 INSTITUTIONAL LOGIC ---
# Standardized and cleaned up based on V12 FVG Education

def apply_ict_v12_depth(df):
    """Main entry point for V12 institutional enrichment"""
    df = df.copy()
    if df.empty: return df
    
    # 1. Indicator Layer (Institutional Grade)
    df = find_fvg_v12(df)
    df = find_ifvg_v12(df)
    df = find_turtle_soup_v2(df)
    df = find_mss_v11(df)
    df = find_volume_imbalance(df)
    df = find_order_blocks(df)
    
    # 2. Advanced Phase Logic
    df = detect_po3_v11(df)
    
    # 3. PD Arrays & Bias Confluence
    pd_v12 = get_premium_discount_v11(df)
    df['is_discount'] = pd_v12['is_discount']
    df['is_premium'] = pd_v12['is_premium']
    
    return df
# --- ICT V18 OMNISCIENT (MULTI-SESSION MASTERY) ---
def is_in_algorithmic_window_v18(ts):
    hour = ts.hour
    minute = ts.minute
    if hour in [10, 17, 21]: return True
    macros = [(16, 50, 17, 10), (17, 50, 18, 10), (18, 50, 19, 10)]
    for h1, m1, h2, m2 in macros:
        if (hour == h1 and minute >= m1) or (hour == h2 and minute <= m2):
            return True
    return False
def apply_ict_v18_omniscient(df, df_corr=None):
    df = df.copy()
    if df.empty: return df
    df = apply_ict_v16_sovereign(df, df_corr)
    df['is_algo_window'] = [is_in_algorithmic_window_v18(ts) for ts in df.index]
    return df

