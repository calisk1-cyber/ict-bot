# Probing the 'dukascopy' library suggested by user
try:
    from dukascopy import Dukascopy
    dc = Dukascopy()
    print("Dukascopy library found and initialized.")
    # Quick test
    data = dc.get_candles(
        instrument='XAUUSD',
        interval='1h',
        start='2025-03-01',
        end='2025-03-24'
    )
    print(f"Success! Fetched {len(data)} bars.")
    data.to_csv("xauusd_probe.csv")
except Exception as e:
    print(f"Error test dukascopy: {e}")
