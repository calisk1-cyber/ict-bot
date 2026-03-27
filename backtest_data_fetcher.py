import yfinance as yf
import pandas as pd
import os

def fetch_backtest_data():
    os.makedirs("backtest_data", exist_ok=True)
    symbols = {
        "EUR_USD": "EURUSD=X", "GBP_USD": "GBPUSD=X", 
        "XAU_USD": "GC=F", "NAS100_USD": "^NDX", "US30_USD": "^DJI"
    }
    for ticker, yf_ticker in symbols.items():
        print(f"Fetching {ticker}...")
        try:
            df_5m = yf.download(yf_ticker, period="1mo", interval="5m")
            df_1h = yf.download(yf_ticker, period="1mo", interval="1h")
            
            # Flatten MultiIndex columns if present
            if isinstance(df_5m.columns, pd.MultiIndex):
                df_5m.columns = df_5m.columns.get_level_values(0)
            if isinstance(df_1h.columns, pd.MultiIndex):
                df_1h.columns = df_1h.columns.get_level_values(0)
                
            df_5m.to_csv(f"backtest_data/{ticker}_5m.csv")
            df_1h.to_csv(f"backtest_data/{ticker}_1h.csv")
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
    print("Backtest data fetch completed.")

if __name__ == "__main__":
    fetch_backtest_data()
