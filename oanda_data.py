import os
import pandas as pd
import oandapyV20
import oandapyV20.endpoints.instruments as instruments
from dotenv import load_dotenv

load_dotenv()

def download_oanda_candles(instrument="EUR_USD", granularity="M5", count=2000):
    """
    Fetches historical candles from Oanda V20 API.
    """
    access_token = os.getenv("OANDA_API_KEY")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    environment = os.getenv("OANDA_ENV", "practice")
    
    if not access_token:
        print("Error: OANDA_API_KEY not found in .env")
        return pd.DataFrame()
        
    client = oandapyV20.API(access_token=access_token, environment=environment)
    
    params = {
        "count": count,
        "granularity": granularity,
        "price": "MBA" # Mid, Bid, Ask
    }
    
    try:
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        client.request(r)
        
        candles = r.response.get('candles', [])
        data = []
        for c in candles:
            if not c['complete']: continue
            row = {
                "Time": c['time'],
                "Open": float(c['mid']['o']),
                "High": float(c['mid']['h']),
                "Low": float(c['mid']['l']),
                "Close": float(c['mid']['c']),
                "Volume": int(c['volume'])
            }
            data.append(row)
            
        df = pd.DataFrame(data)
        df['Time'] = pd.to_datetime(df['Time'])
        df.set_index('Time', inplace=True)
        # Convert to TSİ (GMT+3)
        df.index = df.index.tz_convert('Europe/Istanbul')
        return df
    except Exception as e:
        print(f"Oanda Fetch Error: {e}")
        return pd.DataFrame()

if __name__ == "__main__":
    df = download_oanda_candles()
    print(df.head())
    print(f"Fetched {len(df)} candles.")
