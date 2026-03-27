import requests
import pytz
from datetime import datetime, timezone, timedelta

def is_high_impact_news_active():
    """Detects if high-impact news are currently happening (30min window) using Faireconomy API."""
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    
    try:
        r = requests.get(url, timeout=5)
        events = r.json()
        
        # Use UTC for all comparison
        now = datetime.now(timezone.utc)
        
        for event in events:
            # Check impact level
            impact = event.get('impact', 'Low')
            if impact != 'High': continue
            
            # Parse Date: "2024-09-17T08:30:00-04:00"
            try:
                # Some APIs provide different formats. Standardizing to current time with offset
                # The format in ff_calendar_thisweek is usually a bit simpler or RFC3339
                event_time_str = event.get('date')
                if not event_time_str: continue
                
                # Strip offset and parse or handle accordingly
                event_time = datetime.fromisoformat(event_time_str)
                # Ensure UTC if it's offset-aware
                if event_time.tzinfo:
                    event_time = event_time.astimezone(timezone.utc)
                else:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                
                # 30-minute safety buffer (before and after)
                diff = abs((now - event_time).total_seconds())
                if diff < 1800: # 30 minutes in seconds
                    return True, event.get('title', 'Unknown News Event')
            except Exception as e:
                print(f"Error parsing event: {e}")
                continue
                
        return False, None
    except Exception as e:
        print(f"News API Connection Error: {e}")
        return False, None

if __name__ == "__main__":
    active, name = is_high_impact_news_active()
    if active: print(f"--- VOLATILITY ALERT: {name} ---")
    else: print("--- FINANCIAL CALENDAR STABLE ---")
