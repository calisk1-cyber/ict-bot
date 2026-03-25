import sys
import os
import pandas as pd
from data_fetcher import download_dukascopy_mtf

# Add current directory to path
sys.path.append(os.getcwd())

def main():
    ticker = "EURUSD"
    # Son 1 yil: 2025-01-01 -> 2026-01-01
    start_date = "2024-03-01"
    end_date = "2025-03-24"
    
    print(f"[{ticker}] 1 Yillik MTF Veri Indiriliyor ({start_date} - {end_date})...")
    
    # download_dukascopy_mtf(ticker, start_date, end_date)
    # Bu fonksiyon eurusd_1m.csv, eurusd_5m.csv vs. dosyalarini olusturur.
    # Not: dukascopy-python instrument olarak 'EURUSD' (noktasiz) bekleyebilir, 
    # data_fetcher icinde bunu handle etmistik.
    
    try:
        download_dukascopy_mtf(ticker, start_date, end_date)
        print("\n[SUCCESS] Tum veriler indirildi ve CSV olarak kaydedildi.")
    except Exception as e:
        print(f"\n[ERROR] Veri indirme hatasi: {e}")

if __name__ == "__main__":
    main()
