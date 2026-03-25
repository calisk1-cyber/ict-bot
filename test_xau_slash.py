import dukascopy_python as dp
from datetime import datetime
import pandas as pd

def test_fetch():
    print("Fetching 1h XAU/USD 1 week data directly...")
    start = datetime(2025, 3, 1)
    end = datetime(2025, 3, 24)
    try:
        data = dp.fetch(
            instrument="XAU/USD", # Added slash
            interval=dp.INTERVAL_HOUR_1,
            offer_side=dp.OFFER_SIDE_BID,
            start=start,
            end=end,
            debug=True
        )
        print(f"Success! Fetched {len(data)} bars.")
        data.to_csv("xauusd_test_slash.csv")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_fetch()
