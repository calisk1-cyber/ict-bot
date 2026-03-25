import yfinance as yf
import pandas as pd
import datetime

def download_yf_mtf(ticker="EURUSD=X"):
    print(f"Downloading 1-year MTF data from yfinance for {ticker}...")
    # yfinance uses symbols like EURUSD=X for Forex
    # 1h data for 1 year
    df_1h = yf.download(ticker, period="1y", interval="1h")
    if not df_1h.empty:
        # Flatten MultiIndex if present
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = df_1h.columns.get_level_values(0)
        
        df_1h.to_csv("eurusd_1h.csv")
        print(f"1h data saved: {len(df_1h)} bars.")
    
    # yfinance doesn't support 4h directly (only 1h, 1d, etc.)
    # We can resample 1h to 4h
    if not df_1h.empty:
        df_4h = df_1h.resample('4h').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        df_4h.to_csv("eurusd_4h.csv")
        print(f"4h data resampled and saved: {len(df_4h)} bars.")
    
    # 5m data (only last 60 days allowed by yfinance)
    df_5m = yf.download(ticker, period="60d", interval="5m")
    if not df_5m.empty:
        df_5m.to_csv("eurusd_5m.csv")
        print(f"5m data saved (60d): {len(df_5m)} bars.")

if __name__ == "__main__":
    download_yf_mtf()
