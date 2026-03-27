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
    for i in range(5, len(df)):
        if df['Close'].iloc[i] > df['High'].iloc[i-2] and df['High'].iloc[i-2] > df['Low'].iloc[i]:
            df.loc[df.index[i], 'IFVG_Bull'] = True
        elif df['Close'].iloc[i] < df['Low'].iloc[i-2] and df['Low'].iloc[i-2] < df['High'].iloc[i]:
            df.loc[df.index[i], 'IFVG_Bear'] = True
    return df

def find_turtle_soup_v2(df, lookback=20):
    """Advanced Liquidity Sweep Detection"""
    df = df.copy()
    high_level = df['High'].shift(1).rolling(lookback).max()
    low_level = df['Low'].shift(1).rolling(lookback).min()
    # Sweep + Rejection
    df['TurtleSoup_Bull'] = (df['Low'] < low_level) & (df['Close'] > low_level)
    df['TurtleSoup_Bear'] = (df['High'] > high_level) & (df['Close'] < high_level)
    return df

def detect_amd_phases_v2(df):
    """
    AMD: Accumulation, Manipulation, Distribution phases.
    Accumulation: Low volatility, tight range (Asian session).
    Manipulation: False move sweeping accumulation range (London).
    Distribution: Primary trend move (NY).
    """
    df = df.copy()
    df['AMD_Accumulation'] = False
    df['AMD_Manipulation'] = False
    df['AMD_Distribution'] = False
    
    # Logic: Identify local ranges and look for breaks followed by reversals
    vol = df['Close'].diff().abs().rolling(10).mean()
    avg_vol = vol.rolling(50).mean()
    df['AMD_Accumulation'] = vol < (avg_vol * 0.7)
    
    return df

def find_order_blocks_v2(df):
    """Identify High-Probability Institutional Order Blocks"""
    df = df.copy()
    df['OB_Bull'] = False
    df['OB_Bear'] = False
    
    for i in range(2, len(df)):
        # Bullish OB: Last down candle before displacement up
        if df['Close'].iloc[i] > df['High'].iloc[i-1] and df['Close'].iloc[i-1] < df['Open'].iloc[i-1]:
            df.loc[df.index[i], 'OB_Bull'] = True
        # Bearish OB: Last up candle before displacement down
        if df['Close'].iloc[i] < df['Low'].iloc[i-1] and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]:
            df.loc[df.index[i], 'OB_Bear'] = True
    return df

def find_ipda_v2(df):
    """Interbank Price Delivery Algorithm (IPDA) - Data Ranges & Reference Points"""
    df = df.copy()
    df['IPDA_High_20'] = df['High'].rolling(20).max()
    df['IPDA_Low_20'] = df['Low'].rolling(20).min()
    df['IPDA_Equilibrium'] = (df['IPDA_High_20'] + df['IPDA_Low_20']) / 2
    return df

def find_liquidity_sweep_v2(df):
    """Detects sweeps of key swing highs/lows"""
    return find_turtle_soup_v2(df)

def find_smt_divergence_v2(df_main, df_corr):
    """Institutional Correlation Check"""
    return find_smt_divergence(df_main, df_corr)

def find_mss_v2(df, lookback=5):
    """Market Structure Shift (MSS) / CHoCH"""
    df = df.copy()
    df['MSS_Bull'] = (df['Close'] > df['High'].shift(1).rolling(lookback).max())
    df['MSS_Bear'] = (df['Close'] < df['Low'].shift(1).rolling(lookback).min())
    return df

def find_silver_bullet(df):
    """Silver Bullet Signal: FVG within SB window + MSS"""
    df = df.copy()
    # middle candle body size vs avg
    res = find_fvg_v3(df)
    res = find_mss_v2(res)
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

def get_htf_bias(ticker):
    """
    4H ve 1D grafiklerde ana yönü tayin eder.
    Döner: 'BULLISH', 'BEARISH', 'NEUTRAL'
    """
    try:
        # 1. 4H Verisini Çek
        df_4h = download_full_history(ticker, interval='1h', period='7d') # 4H yerine 1H kümülatif bakabiliriz
        if df_4h.empty: return "NEUTRAL"
        
        # Basit EMA ve RSI Filtresi
        ema_20 = ta.ema(df_4h['Close'], length=20)
        rsi = ta.rsi(df_4h['Close'], length=14)
        
        last_price = df_4h['Close'].iloc[-1]
        last_ema = ema_20.iloc[-1]
        last_rsi = rsi.iloc[-1]
        
        if last_price > last_ema and last_rsi > 50:
            return "BULLISH"
        elif last_price < last_ema and last_rsi < 50:
            return "BEARISH"
        else:
            return "NEUTRAL"
    except:
        return "NEUTRAL"

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


# --- EVOLVED LOGIC (Autonomous R&D) ---
def premium_discount_zones(df, long_threshold=0.5):
    """
    Determine the premium/discount zones for trading and filter trades based on these zones.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing 'high', 'low', and 'close' prices.
    long_threshold : float
        The threshold percentage below which it is considered a discount zone (0 < long_threshold < 1).
    
    Returns
    -------
    pd.DataFrame
        Updated DataFrame with a new column 'discount_zone' indicating if the close is in the discount zone.
    """
    high = df['high'].max()
    low = df['low'].min()
    discount_level = low + (high - low) * long_threshold

    df['discount_zone'] = df['close'] < discount_level
    return df


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def daily_open_cross(df: pd.DataFrame, london_open_time: str = '08:00', daily_open_col: str = 'Open', london_open_col: str = 'London_Open') -> pd.Series:
    """
    Calculates the relationship between the London open and the Daily open.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing at least the daily open prices and a datetime index.
    london_open_time (str): The time indicating the London open, default is '08:00'.
    daily_open_col (str): The name of the column with daily open prices.
    london_open_col (str): The name of the column to be created with London open prices.

    Returns:
    pd.Series: A series indicating whether the London open price crosses above or below the daily open price.
    """
    # Extracting the London open prices based on the specified time.
    df[london_open_col] = df.between_time(london_open_time, london_open_time)[daily_open_col]

    # Forward fill to ensure the London open price is reflected for the entire day
    df[london_open_col] = df[london_open_col].ffill()

    signal = (df[london_open_col] > df[daily_open_col]).astype(int) - (df[london_open_col] < df[daily_open_col]).astype(int)
    return signal


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd
import numpy as np

def premium_discount_zones(data: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """
    Calculates the premium and discount zones for a given price dataset.
    A price in the lower half of the range is considered in the discount zone,
    and only long trades should be considered in this zone.
    
    Parameters:
    - data: pd.DataFrame with a 'close' column containing the price data.
    - window: int, optional. The period over which the premium/discount zones are calculated.
    
    Returns:
    - pd.DataFrame with 'premium_zone' and 'discount_zone' columns.
    """
    high = data['close'].rolling(window=window).max()
    low = data['close'].rolling(window=window).min()
    mid_level = (high + low) / 2
    
    # Determine premium and discount zones
    data['premium_zone'] = data['close'] > mid_level
    data['discount_zone'] = data['close'] <= mid_level
    
    return data


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd
import numpy as np

def premium_discount_zones(df, lookback_period=14, discount_threshold=0.5):
    """
    Identifies whether the current price is in a discount zone.
    
    :param df: DataFrame with columns ['close'].
    :param lookback_period: Period to look back for high and low.
    :param discount_threshold: The threshold to determine the discount zone relative to the range.
    :return: Column 'discount_zone' added to DataFrame, where True indicates the price is in a discount zone.
    """
    
    # Calculate the high and low over the lookback period
    high = df['close'].rolling(window=lookback_period).max()
    low = df['close'].rolling(window=lookback_period).min()
    
    # Calculate the premium and discount levels
    discount_level = low + discount_threshold * (high - low)
    
    # Determine if the current price is in the discount zone
    df['discount_zone'] = df['close'] < discount_level
    
    return df


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def mss_entry_signal(df, period: int = 5):
    """
    MSS: Closing above/below recent high/low as entry signal.
    
    Args:
    df (pd.DataFrame): DataFrame containing 'close' price series.
    period (int): Number of periods to consider for recent high/low.

    Returns:
    pd.Series: Signals series with 1 for buy, -1 for sell, 0 for no signal.
    """
    df['recent_high'] = df['close'].rolling(window=period).max()
    df['recent_low'] = df['close'].rolling(window=period).min()

    # Entry signal: 1 for buy if close > recent high, -1 for sell if close < recent low
    buy_signal = (df['close'] > df['recent_high']).astype(int)
    sell_signal = (df['close'] < df['recent_low']).astype(int) * -1

    # Combine signals
    df['signal'] = buy_signal + sell_signal

    return df['signal']


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def mss_entry_signal(data: pd.DataFrame, recent_period: int = 5) -> pd.DataFrame:
    """
    MSS: Identify entry signals based on closing above/below recent high/low.

    Parameters
    ----------
    data : pd.DataFrame
        A DataFrame with 'high', 'low', and 'close' columns.
    recent_period : int, optional
        Number of recent periods to consider for highs and lows, by default 5.

    Returns
    -------
    pd.DataFrame
        Original DataFrame with additional 'mss_entry_signal' column indicating entry signals.

    Signals
    -------
    - 1: Buy Signal (Close above recent high)
    - -1: Sell Signal (Close below recent low)
    - 0: No Signal
    """
    data['recent_high'] = data['high'].rolling(window=recent_period).max()
    data['recent_low'] = data['low'].rolling(window=recent_period).min()

    data['mss_entry_signal'] = 0
    data.loc[data['close'] > data['recent_high'].shift(1), 'mss_entry_signal'] = 1
    data.loc[data['close'] < data['recent_low'].shift(1), 'mss_entry_signal'] = -1

    data.drop(['recent_high', 'recent_low'], axis=1, inplace=True)

    return data


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def premium_discount_zones(df, column='close', window=14):
    """
    This function calculates the premium/discount zones for trading.
    Only trade in discount for long positions.
    
    Parameters:
    df (pd.DataFrame): Dataframe containing the market data.
    column (str): The column name to analyze. Default is 'close'.
    window (int): The lookback window to calculate the zones. Default is 14.
    
    Returns:
    pd.DataFrame: DataFrame with 'premium_zone' and 'discount_zone' columns.
    """
    df['rolling_high'] = df[column].rolling(window=window).max()
    df['rolling_low'] = df[column].rolling(window=window).min()
    df['midpoint'] = (df['rolling_high'] + df['rolling_low']) / 2
    df['premium_zone'] = df['midpoint'] + (df['rolling_high'] - df['midpoint']) / 2
    df['discount_zone'] = df['midpoint'] - (df['midpoint'] - df['rolling_low']) / 2
    
    return df[['premium_zone', 'discount_zone']]


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def apply_mss_signal(data: pd.DataFrame, recent_period: int = 5) -> pd.DataFrame:
    """
    Applies Market Structure Shift (MSS) based on closing above/below recent highs/lows as an entry signal.
    
    Parameters:
    data (pd.DataFrame): DataFrame containing the OHLC data with 'close', 'high', 'low'.
    recent_period (int): The number of periods to consider for recent highs and lows.

    Returns:
    pd.DataFrame: The DataFrame with an additional column 'mss_signal'.
    """
    data['recent_high'] = data['high'].rolling(window=recent_period).max().shift(1)
    data['recent_low'] = data['low'].rolling(window=recent_period).min().shift(1)
    
    conditions = [
        (data['close'] > data['recent_high']),  # Closing above recent high
        (data['close'] < data['recent_low']),  # Closing below recent low
    ]
    choices = ['long_entry', 'short_entry']

    data['mss_signal'] = np.select(conditions, choices, default=None)
    return data


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def premium_discount_zones(df, threshold=0.5):
    """
    Identify Premium and Discount zones for trading. Only trade in discount for longs. 

    Parameters:
    df (pd.DataFrame): DataFrame with at least 'high', 'low', 'close' columns.
    threshold (float): A threshold value between 0 and 1 to define the discount zone.

    Returns:
    pd.Series: A series indicating if the close is in a discount zone (1 for yes, 0 for no).
    """
    df['range'] = df['high'] - df['low']
    df['discount_zone'] = df['low'] + threshold * df['range']
    df['in_discount'] = df['close'] < df['discount_zone']
    return df['in_discount'].astype(int)


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd
import numpy as np

def premium_discount_zones(df, reference_col='close', threshold=0.5):
    """
    Identify premium and discount zones in the provided DataFrame and mark them for trading consideration.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing market data with at least one column for price reference.
    reference_col (str): Column name to be used as a reference for premium and discount zone calculation.
    threshold (float): Percentage to define zone boundaries (e.g., 0.5 for 50% premium/discount).
    
    Returns:
    pd.DataFrame: DataFrame with columns for premium and discount zones.
    """
    # Calculate rolling high and low
    high = df[reference_col].rolling(window=20, min_periods=1).max()
    low = df[reference_col].rolling(window=20, min_periods=1).min()
    
    # Calculate mid point
    midpoint = (high + low) / 2
    
    # Define premium and discount thresholds
    premium_threshold = midpoint + (midpoint * threshold / 100)
    discount_threshold = midpoint - (midpoint * threshold / 100)
    
    # Determine premium and discount zones
    df['premium_zone'] = np.where(df[reference_col] > premium_threshold, True, False)
    df['discount_zone'] = np.where(df[reference_col] < discount_threshold, True, False)
    
    return df


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd
import numpy as np

def premium_discount_zones(df, pivot_col='close', threshold=0.5, zone_col='zone'):
    """
    Adds a column to the dataframe that indicates the market zone relative to the premium or discount.
    This can be used to filter trades only in the discount zone for longs.

    Parameters:
    df (pd.DataFrame): DataFrame containing at least 'high', 'low', and 'close' prices.
    pivot_col (str): The column to use for calculating the mid-level, typically the 'close'.
    threshold (float): The threshold to determine premium (above 0.5) or discount (below 0.5) zones.
    zone_col (str): The name of the column to add for zone categorization.

    Returns:
    pd.DataFrame: Modified DataFrame including the zone information.
    """

    # Calculate mid-level
    mid = (df['high'] + df['low']) / 2

    # Calculate zone value
    df['zone_value'] = (df[pivot_col] - df['low']) / (df['high'] - df['low'])

    # Classify zones based on threshold
    df[zone_col] = np.where(df['zone_value'] < threshold, 'Discount', 'Premium')
    
    # Drop temporary 'zone_value' column
    df.drop(columns=['zone_value'], inplace=True)
    
    return df


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd
import numpy as np
import pandas_ta as ta

def mss_entry_signal(data: pd.DataFrame, high_col: str = 'High', low_col: str = 'Low', close_col: str = 'Close') -> pd.Series:
    """
    MSS Entry Signal: Generates entry signals based on market structure shift (MSS), identifying
    when the closing price is above a recent high or below a recent low, which could be a signal
    for a potential entry.

    Parameters:
    - data: pd.DataFrame containing the market data with columns for high, low, and close prices.
    - high_col: str, default 'High', column name for high prices
    - low_col: str, default 'Low', column name for low prices
    - close_col: str, default 'Close', column name for close prices

    Returns:
    - pd.Series of entry signals: 1 for bullish entry, -1 for bearish entry, and 0 for no signal.
    """
    recent_high = data[high_col].rolling(window=5).max().shift(1)
    recent_low = data[low_col].rolling(window=5).min().shift(1)

    bullish_entry = (data[close_col] > recent_high).astype(int)
    bearish_entry = (data[close_col] < recent_low).astype(int) * -1

    return bullish_entry + bearish_entry


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd
import pandas_ta as ta

def daily_open_cross(df: pd.DataFrame, london_open_hour: int = 8) -> pd.DataFrame:
    """
    Calculate the daily open cross signal between London open and Daily open.
    
    Parameters:
    df : pd.DataFrame
        DataFrame having 'Open' prices with DateTime index with at least hourly resolution.
    london_open_hour : int
        The hour (in 24-hour format) representing London market open. Default is 8.
        
    Returns:
    pd.DataFrame
        A DataFrame with an additional column 'DOC Signal' indicating:
        1 if London open is above Daily open (bullish signal), 
        -1 if London open is below Daily open (bearish signal), or 
        0 if they are equal.
    """
    df = df.copy()
    if not df.index.is_monotonic_increasing:
        df.sort_index(inplace=True)

    # Identify the daily open index
    daily_open = df.resample('D').first()
    daily_open['Daily Open'] = daily_open['Open']
    df['Daily Open'] = daily_open['Daily Open'].reindex(df.index, method='ffill')

    # Identify the London open based on london_open_hour
    london_open_time = df.between_time(f"{london_open_hour}:00", f"{london_open_hour}:00", inclusive="left")
    london_open = london_open_time.resample('D').first()
    df['London Open'] = london_open['Open'].reindex(df.index, method='ffill')

    # Calculate DOC Signal
    df['DOC Signal'] = (df['London Open'] > df['Daily Open']).astype(int) - (df['London Open'] < df['Daily Open']).astype(int)

    # Clean up auxiliary columns
    return df.drop(columns=['Daily Open', 'London Open'])


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def premium_discount_zones(df, zone_col='PremiumDiscountZone'):
    """
    Identifies premium and discount zones in the market data for trading strategy.
    A market is considered in discount if the current price is in the lower half of the previous day's range.
    
    Args:
        df (pd.DataFrame): DataFrame with OHLC data, indexed by DateTime, must include 'High', 'Low', and 'Close'.
        zone_col (str): Name of the column to add with premium/discount zone information.
        
    Returns:
        pd.DataFrame: DataFrame with added column indicating premium or discount zone.
    """
    # Calculating the previous day's high and low
    df['Previous_High'] = df['High'].shift(1)
    df['Previous_Low'] = df['Low'].shift(1)
    
    # Calculating the midpoint
    df['Midpoint'] = (df['Previous_High'] + df['Previous_Low']) / 2
    
    # Determining if the current close price is in discount (below the mid point)
    df[zone_col] = 'Premium'
    df.loc[df['Close'] < df['Midpoint'], zone_col] = 'Discount'

    # Drop temporary columns
    df.drop(['Previous_High', 'Previous_Low', 'Midpoint'], axis=1, inplace=True)
    
    return df


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def mss_entry_signal(df: pd.DataFrame, period: int = 14):
    """
    Identifies MSS entry signals where the closing price crosses above a recent high or below a recent low.

    Parameters:
    - df (pd.DataFrame): The dataframe containing `close` prices.
    - period (int): The lookback period to determine recent high and low. Default is 14.

    Returns:
    - pd.DataFrame: DataFrame with an added 'mss_signal' column indicating entry signals. 1 for long, -1 for short.
    """
    high_rolling = df['close'].rolling(window=period).max()
    low_rolling = df['close'].rolling(window=period).min()
    
    df['mss_signal'] = 0
    df.loc[df['close'] > high_rolling.shift(1), 'mss_signal'] = 1
    df.loc[df['close'] < low_rolling.shift(1), 'mss_signal'] = -1
    
    return df


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def mss_entry_signal(df, period=20):
    """
    Implements the MSS strategy by checking if the closing price
    is above/below the recent high/low as an entry signal.
    
    :param df: DataFrame containing at least 'High', 'Low', and 'Close' columns
    :param period: The period over which to check recent high/low
    :return: DataFrame with an additional column 'MSS_Entry_Signal'
    """
    df['Recent_High'] = df['High'].rolling(window=period).max()
    df['Recent_Low'] = df['Low'].rolling(window=period).min()
    
    conditions = [
        (df['Close'] > df['Recent_High']),
        (df['Close'] < df['Recent_Low'])
    ]
    choices = [1, -1]  # 1 for a long entry signal, -1 for a short entry signal
    
    df['MSS_Entry_Signal'] = np.select(conditions, choices, default=0)
    
    # Drop temporary columns
    df.drop(['Recent_High', 'Recent_Low'], axis=1, inplace=True)
    
    return df


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd
import numpy as np

def mss_entry_signal(df: pd.DataFrame, lookback_period: int = 10) -> pd.Series:
    """
    Identify MSS (Market Structure Shift) entry signals based on the latest 
    R&D finding. A signal is generated when the closing price is above the 
    recent high or below the recent low over a specified lookback period.

    :param df: DataFrame with 'close' prices.
    :param lookback_period: Number of periods to look back for high/low comparison.
    :return: A Pandas Series indicating buy (1), sell (-1), or hold (0) signals.
    """
    # Calculate rolling high and low
    recent_high = df['close'].rolling(window=lookback_period).max()
    recent_low = df['close'].rolling(window=lookback_period).min()
    
    # Generate entry signals
    buy_signal = (df['close'] > recent_high).astype(int)
    sell_signal = (df['close'] < recent_low).astype(int) * -1
    
    # Combine signals: 1 for buy, -1 for sell, 0 for hold
    signals = buy_signal + sell_signal
    
    return signals


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd
import numpy as np
import pandas_ta as ta

def premium_discount_zones(df, window=20):
    """
    Identifies premium and discount zones based on the high-low ranges over a specified period.

    Parameters:
    df (pd.DataFrame): DataFrame containing market data with at least 'high', 'low', and 'close' columns.
    window (int): The look-back period for calculating the highest high and lowest low.

    Returns:
    pd.DataFrame: DataFrame with 'premium' and 'discount' zones.
    """
    df = df.copy()
    
    # Calculate the highest high and lowest low over the given window
    df['highest_high'] = df['high'].rolling(window=window).max()
    df['lowest_low'] = df['low'].rolling(window=window).min()
    
    # Calculate the midline of the range
    df['midline'] = (df['highest_high'] + df['lowest_low']) / 2
    
    # Determine premium and discount zones
    df['premium'] = df['close'] > df['midline']
    df['discount'] = df['close'] <= df['midline']
    
    return df[['premium', 'discount']]


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def mss_entry_signal(data: pd.DataFrame, high_column: str, low_column: str, close_column: str) -> pd.Series:
    """
    Identifies MSS entry signals in the given data using closing prices above or below recent high/low.
    
    Parameters:
    - data (pd.DataFrame): DataFrame containing market data.
    - high_column (str): The column name representing the high prices in the data.
    - low_column (str): The column name representing the low prices in the data.
    - close_column (str): The column name representing the closing prices in the data.

    Returns:
    - pd.Series: A series with entry signals: 1 for long entry, -1 for short entry, 0 for no signal.
    """
    highs = data[high_column]
    lows = data[low_column]
    close = data[close_column]
    
    prev_high = highs.shift(1)
    prev_low = lows.shift(1)
    
    long_entries = close > prev_high
    short_entries = close < prev_low
    
    signal = pd.Series(0, index=data.index)
    signal[long_entries] = 1
    signal[short_entries] = -1
    
    return signal


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def mss_entry_signal(df, column_high='high', column_low='low', column_close='close'):
    """
    Implements the MSS entry signal based on closing above/below recent high/low.
    Args:
        df (pd.DataFrame): A pandas DataFrame with market data including high, low, and close columns.
        column_high (str): The column name for high prices. Default is 'high'.
        column_low (str): The column name for low prices. Default is 'low'.
        column_close (str): The column name for close prices. Default is 'close'.

    Returns:
        pd.Series: A pandas Series with entry signals where 1 indicates a long entry setup and -1 a short entry setup.
    """
    signals = pd.Series(0, index=df.index)

    # Shift the high and low to represent recent high and low for the previous bar
    recent_high = df[column_high].shift(1)
    recent_low = df[column_low].shift(1)

    # Generate signals for closing above recent high or below recent low
    long_signals = (df[column_close] > recent_high).astype(int)
    short_signals = (df[column_close] < recent_low).astype(int) * -1

    # Combine long and short signals
    signals = long_signals + short_signals
    
    return signals


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd
import numpy as np

def calculate_daily_open_cross(data):
    """
    Calculate the London open vs Daily open relationship.
    
    Parameters:
    data (pd.DataFrame): DataFrame containing 'Date', 'Time', 'Open', 'High', 'Low', 'Close' columns.
    
    Returns:
    pd.Series: A Series indicating the London open vs Daily open relationship.
    """
    # Ensure 'Date' and 'Time' are combined and converted to datetime
    data['DateTime'] = pd.to_datetime(data['Date'] + ' ' + data['Time'])
    data.set_index('DateTime', inplace=True)
    
    # Define London open and Daily open times
    london_open_time = '08:00:00'
    daily_open_time = '00:00:00'
    
    # Calculate daily open price
    daily_open = data.between_time(daily_open_time, daily_open_time)['Open'].resample('D').first()
    
    # Calculate London open price
    london_open = data.between_time(london_open_time, london_open_time)['Open'].resample('B').first()
    
    # Calculate the relationship
    relationship = np.where(london_open > daily_open.shift(1), 'Above', 'Below')
    
    return pd.Series(relationship, index=daily_open.index, name='London_vs_Daily_Open')


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def mss_entry_signal(data: pd.DataFrame, high_col: str, low_col: str, close_col: str, period: int = 5) -> pd.DataFrame:
    """
    This function identifies entry signals based on the Market Structure Shift (MSS) strategy.

    Parameters:
    data (pd.DataFrame): A DataFrame containing at least high, low, and close prices.
    high_col (str): The name of the column representing the high prices.
    low_col (str): The name of the column representing the low prices.
    close_col (str): The name of the column representing the close prices.
    period (int): The lookback period for recent high/low. Default is 5.

    Returns:
    pd.DataFrame: DataFrame with added columns 'MSS_Buy_Signal' and 'MSS_Sell_Signal'.
    """
    data['Recent_High'] = data[high_col].rolling(window=period).max()
    data['Recent_Low'] = data[low_col].rolling(window=period).min()

    # Entry signals
    data['MSS_Buy_Signal'] = (data[close_col] > data['Recent_High']).astype(int)
    data['MSS_Sell_Signal'] = (data[close_col] < data['Recent_Low']).astype(int)

    # Clean up
    data.drop(['Recent_High', 'Recent_Low'], axis=1, inplace=True)

    return data


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def mss_entry_signal(prices_df):
    """
    Membrane Sweep Strategy: Closing above/below recent high/low as entry signal.

    Parameters:
        prices_df (pd.DataFrame): DataFrame with 'high', 'low', and 'close' columns.

    Returns:
        pd.Series: A series with entry signals (1 for long, -1 for short, 0 for no signal).
    """
    recent_high = prices_df['high'].rolling(window=3, min_periods=1).max().shift(1)
    recent_low = prices_df['low'].rolling(window=3, min_periods=1).min().shift(1)

    entry_signals = pd.Series(0, index=prices_df.index)
    entry_signals[prices_df['close'] > recent_high] = 1
    entry_signals[prices_df['close'] < recent_low] = -1

    return entry_signals


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd
import numpy as np

def mss_entry_signals(data, period=14):
    """
    MSS: Detects entry signals where closing price is above/below the 
    recent high/low over a specified period.
    
    Parameters:
    - data: DataFrame with a 'Close' price column
    - period: Lookback period for determining recent highs/lows
    
    Returns:
    - DataFrame with 'MSS_Long_Signal' and 'MSS_Short_Signal' columns
    """

    data = data.copy()

    # Calculate moving high and low over the specified period
    data['Recent_High'] = data['Close'].rolling(window=period).max()
    data['Recent_Low'] = data['Close'].rolling(window=period).min()

    # Determine entry signals
    data['MSS_Long_Signal'] = np.where(data['Close'] > data['Recent_High'], 1, 0)
    data['MSS_Short_Signal'] = np.where(data['Close'] < data['Recent_Low'], 1, 0)

    # Drop intermediate columns
    data.drop(['Recent_High', 'Recent_Low'], axis=1, inplace=True)

    return data[['MSS_Long_Signal', 'MSS_Short_Signal']]


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd
import numpy as np

def mss_signal(df, period=14, price_col='close'):
    """
    MSS Closing Signal: Determines if the closing price is above/below recent high/low as entry signal.
    
    Parameters:
    df (pd.DataFrame): The dataframe containing market data
    period (int): Number of periods to look back for high/low
    price_col (str): Column name for the closing price

    Returns:
    pd.Series: A series with entry signals - 1 for long entry, -1 for short entry, 0 for no entry
    """
    recent_highs = df[price_col].rolling(window=period).max()
    recent_lows = df[price_col].rolling(window=period).min()
    
    long_signal = df[price_col] > recent_highs.shift(1)
    short_signal = df[price_col] < recent_lows.shift(1)
    
    signals = np.where(long_signal, 1, np.where(short_signal, -1, 0))
    
    return pd.Series(signals, index=df.index, name='mss_signal')


# --- EVOLVED LOGIC (Autonomous R&D) ---
import pandas as pd

def premium_discount_filter(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """
    Identifies premium and discount zones and filters signals accordingly.
    Only allows trades in discount zones for long trades.
    
    Parameters:
    - df: DataFrame containing at least ['high', 'low', 'close'] columns 
    - lookback: Number of periods to look back for determining zones
    
    Returns:
    - DataFrame with an additional column 'trade_signal' that indicates LONG (1) in discount zones, 
      SHORT (-1) in premium zones, or NEUTRAL (0) otherwise
    """
    df = df.copy()
    
    # Calculate highest high and lowest low
    df['highest_high'] = df['high'].rolling(lookback).max()
    df['lowest_low'] = df['low'].rolling(lookback).min()
    
    # Calculate the midrange
    df['midrange'] = (df['highest_high'] + df['lowest_low']) / 2
    
    # Determine trading zones
    df['trade_zone'] = 'neutral'
    df.loc[df['close'] < df['midrange'], 'trade_zone'] = 'discount'
    df.loc[df['close'] > df['midrange'], 'trade_zone'] = 'premium'
    
    # Generate trade signals based on zones
    df['trade_signal'] = 0  # Default is NEUTRAL
    df.loc[df['trade_zone'] == 'discount', 'trade_signal'] = 1  # LONG
    df.loc[df['trade_zone'] == 'premium', 'trade_signal'] = -1  # SHORT
    
    return df
