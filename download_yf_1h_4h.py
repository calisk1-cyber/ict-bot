import yfinance as yf
import pandas as pd
import datetime

def main():
    ticker = "EURUSD=X"
    print(f"[{ticker}] yfinance ile 1 yillik veri indiriliyor...")
    
    # 1h data (max 730 days)
    df_1h = yf.download(ticker, period="1y", interval="1h", progress=True)
    if not df_1h.empty:
        if isinstance(df_1h.columns, pd.MultiIndex): df_1h.columns = df_1h.columns.droplevel(1)
        df_1h.to_csv("eurusd_1h.csv")
        print(f"1h indirildi: {len(df_1h)} bar")
    
    # 4h data
    # yfinance 4h is only available for some periods or as a resample of 1h
    # Better to download 1h and resample to 4h to be sure
    if not df_1h.empty:
        df_4h = df_1h.resample('4h').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        df_4h.to_csv("eurusd_4h.csv")
        print(f"4h resampled ve kaydedildi: {len(df_4h)} bar")

    # 1d data for bias
    df_1d = yf.download(ticker, period="2y", interval="1d", progress=True)
    if not df_1d.empty:
        if isinstance(df_1d.columns, pd.MultiIndex): df_1d.columns = df_1d.columns.droplevel(1)
        df_1d.to_csv("eurusd_1d.csv")
        print(f"1d indirildi: {len(df_1d)} bar")

if __name__ == "__main__":
    main()
