import os
from dotenv import load_dotenv
load_dotenv(override=True)
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

try:
    client = CryptoHistoricalDataClient(api_key=API_KEY, secret_key=SECRET_KEY)
    request_params = CryptoBarsRequest(
        symbol_or_symbols=["BTC/USD"],
        timeframe=TimeFrame.Day,
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 10)
    )
    bars = client.get_crypto_bars(request_params)
    print("Crypto works.")
except Exception as e:
    print("Crypto Error:", e)

# Test if Alpaca supports EUR/USD
try:
    # Forex in Alpaca? Some say they don't support it natively for free or it requires different endpoints.
    request_params = CryptoBarsRequest(
        symbol_or_symbols=["EUR/USD"],
        timeframe=TimeFrame.Day,
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 10)
    )
    bars = client.get_crypto_bars(request_params)
    print("Forex EUR/USD df:")
    print(bars.df)
except Exception as e:
    print("Forex via Crypto Error:", e)

try:
    client_stock = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    request_params = StockBarsRequest(
        symbol_or_symbols=["EUR/USD", "EURUSD=X", "EURUSD"],
        timeframe=TimeFrame.Day,
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 10)
    )
    bars = client_stock.get_stock_bars(request_params)
    print("Forex via Stock works.")
except Exception as e:
    print("Forex via Stock Error:", e)
