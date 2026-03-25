import yfinance as yf
import pandas as pd

def main():
    ticker = "GC=F"
    print(f"[{ticker}] yfinance ile 30 gunluk veri indiriliyor...")
    
    # 30 days of 5m (max 60 days on yf)
    df_5m = yf.download(ticker, period="1mo", interval="5m", progress=True)
    if not df_5m.empty:
        if isinstance(df_5m.columns, pd.MultiIndex): df_5m.columns = df_5m.columns.droplevel(1)
        df_5m.to_csv("gc=f_5m.csv")
        print(f"5m indirildi: {len(df_5m)} bar")

    # 15m data
    df_15m = yf.download(ticker, period="1mo", interval="15m", progress=True)
    if not df_15m.empty:
        if isinstance(df_15m.columns, pd.MultiIndex): df_15m.columns = df_15m.columns.droplevel(1)
        df_15m.to_csv("gc=f_15m.csv")
        print(f"15m indirildi: {len(df_15m)} bar")

    # 1h data
    df_1h = yf.download(ticker, period="1mo", interval="1h", progress=True)
    if not df_1h.empty:
        if isinstance(df_1h.columns, pd.MultiIndex): df_1h.columns = df_1h.columns.droplevel(1)
        df_1h.to_csv("gc=f_1h.csv")
        print(f"1h indirildi: {len(df_1h)} bar")

if __name__ == "__main__":
    main()
