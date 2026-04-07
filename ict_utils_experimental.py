import pandas as pd
import numpy as np
import pandas_ta as ta

def find_new_logic(df):
    # Ensure the DataFrame has necessary columns
    if not {'high', 'low', 'close', 'open'}.issubset(df.columns):
        raise ValueError("DataFrame must contain 'high', 'low', 'close', 'open' columns")

    # Calculate typical price which is an average of high, low, and close
    df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3

    # Calculate the MA of the typical price
    df['ma_typical'] = df['typical_price'].rolling(window=14).mean()

    # Propose a new logic using the deviation of current price from the moving average of the typical price
    df['deviation'] = (df['close'] - df['ma_typical']) / df['ma_typical']

    # Define threshold for defining 'Significant Deviation'
    threshold = 0.02

    # Generate buy: Significant positive deviation meeting the threshold in oversold conditions
    df['buy_signal'] = (df['deviation'] > threshold) & (df['close'] < df['ma_typical'])

    # Generate sell: Significant negative deviation meeting the threshold in overbought conditions
    df['sell_signal'] = (df['deviation'] < -threshold) & (df['close'] > df['ma_typical'])

    # Determine the final SIGNAL_NEW based on buy/sell signals
    df['SIGNAL_NEW'] = np.where(df['buy_signal'], True, np.where(df['sell_signal'], False, np.nan))

    # Forward fill the signals to ensure continuity in trading logic
    df['SIGNAL_NEW'] = df['SIGNAL_NEW'].ffill().fillna(False)

    return df

# Sample usage:
# df = pd.read_csv('your_data.csv')
# df = find_new_logic(df)
# print(df.tail())