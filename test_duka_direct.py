import dukascopy_python as dp
from datetime import datetime
import pandas as pd

def test_fetch():
    print("Fetching 1h EURUSD 1 year data directly...")
    start = datetime(2025, 1, 1)
    end = datetime(2026, 1, 1)
    try:
        data = dp.fetch(
            instrument="EURUSD",
            interval=dp.INTERVAL_HOUR_1,
            offer_side=dp.OFFER_SIDE_BID,
            start=start,
            end=end,
            debug=True
        )
        print(f"Success! Fetched {len(data)} bars.")
        data.to_csv("eurusd_1h_direct.csv")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_fetch()
