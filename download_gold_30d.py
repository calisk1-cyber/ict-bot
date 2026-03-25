import sys
import os
import pandas as pd
from data_fetcher import download_dukascopy_mtf

# Add current directory to path
sys.path.append(os.getcwd())

def main():
    ticker = "GC=F" # Yahoo ticker
    instrument = "XAUUSD" # Dukascopy instrument
    
    # 30 gun: 2025-02-22 -> 2025-03-24
    start_date = "2025-02-22"
    end_date = "2025-03-24"
    
    print(f"[{instrument}] 30 Gunluk MTF Veri Indiriliyor ({start_date} - {end_date})...")
    
    try:
        # Dukascopy'den XAUUSD olarak çek
        download_dukascopy_mtf(instrument, start_date, end_date)
        print(f"\n[SUCCESS] {instrument} verileri indirildi.")
    except Exception as e:
        print(f"\n[ERROR] Veri indirme hatasi: {e}")

if __name__ == "__main__":
    main()
