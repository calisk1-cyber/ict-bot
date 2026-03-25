import yfinance as yf
import pandas as pd

# SORU 1: VERI DOGRULUGU (Tarih 730 gun limitine gore guncellendi: 2024-04-01)
try:
    df = yf.download('EURUSD=X', 
                      start='2024-04-01',
                      end='2025-03-01',
                      interval='1h')
    
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    
    print("--- HEAD(10) ---")
    print(df.head(10))
    print("\n--- TAIL(10) ---")
    print(df.tail(10))
    print(f"\nToplam satir: {len(df)}")
    print(f"Eksik veri:\n{df.isnull().sum()}")
    if not df.empty:
        print(f"Tarih araligi: {df.index[0]} -> {df.index[-1]}")
    else:
        print("Veri bulunamadi.")
except Exception as e:
    print(f"Hata: {e}")
