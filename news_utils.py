import requests
from datetime import datetime
import pytz

def get_high_impact_news():
    """
    Forex Factory JSON feed'inden bugünkü yüksek etkili haberleri çeker.
    """
    try:
        # Forex Factory JSON feed (Free & Reliable)
        url = "https://nfs.forexfactory.com/ff_calendar_thisweek.json"
        response = requests.get(url, timeout=10)
        events = response.json()
        
        now = datetime.now(pytz.UTC)
        high_impact_events = []
        
        for event in events:
            # Sadece 'High' etkili ve bugünkü haberleri filtrele
            if event['impact'] == 'High':
                event_date = datetime.strptime(event['date'], "%Y-%m-%dT%H:%M:%S%z")
                if event_date.date() == now.date():
                    high_impact_events.append({
                        'title': event['title'],
                        'country': event['country'],
                        'time': event_date
                    })
        return high_impact_events
    except Exception as e:
        print(f"Haber çekme hatası: {e}")
        return []

def is_news_volatile(symbol):
    """
    Belirli bir parite için önümüzdeki 30 dk içinde haber var mı kontrol eder.
    """
    news = get_high_impact_news()
    if not news: return False
    
    now = datetime.now(pytz.UTC)
    relevant_currency = symbol.split('_')[0] # örn: EUR
    if "_" in symbol:
        currencies = symbol.split('_') # EUR, USD
    else:
        currencies = [symbol]

    for event in news:
        if event['country'] in currencies or event['country'] == 'USD':
            time_diff = (event['time'] - now).total_seconds() / 60
            # Haberden 30 dk önce ve 30 dk sonra işlem yapma
            if -30 <= time_diff <= 30:
                return True, event['title']
                
    return False, None
