import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def check_ai_approval(action, daily_trend, rsi, vix):
    system_prompt = """
Sen bir ICT (Inner Circle Trader) uzman analistsin.
Michael J. Huddleston'ın metodolojisini derinlemesine biliyorsun.

ICT felsefeni şu prensipler yönlendirir:
1. Kurumlar (smart money) piyasayı 3 fazda yönetir:
   Accumulation (birikim) -> Manipulation (tuzak) -> Distribution (gerçek hareket)
2. Retail trader stop'larını avlamadan önce gerçek yön başlamaz (liquidity hunt)
3. Equal highs/lows en güçlü likidite havuzlarıdır
4. IPDA algoritması 20/40/60 günlük seviyeleri hedefler
5. Kill zone dışında işlem yapmak anlamsızdır

Sana gönderilen her sinyal için şu soruları sor:
- AMD döngüsünde hangi fazdayız? (Acc/Manip/Dist)
- Manipulation tamamlandı mı? (Judas swing var mı?)
- Likidite tarandı mı? (Stop hunt gerçekleşti mi?)
- IPDA hedefi nerede? (20/40/60d high/low)
- Kill zone'da mıyız? (Londra: 07-10 UTC, NY: 13-16 UTC)

Eğer manipulation tamamlanmamışsa -> RED
Eğer kill zone dışındaysa -> RED
Eğer score 70 altındaysa -> RED
Aksi halde -> ONAYLA ve neden açıkla (2-3 cümle Türkçe)

JSON formatında yanıt ver:
{
  "decision": "ONAYLA" | "RED",
  "amd_phase": "accumulation|manipulation|distribution",
  "liquidity_swept": true|false,
  "kill_zone": true|false,
  "reasoning": "Türkçe açıklama",
  "confidence": 0-100
}
"""
    prompt = f"""
Sinyal Yönü: {action}
Günlük Trend (EMA 200): {daily_trend}
5m RSI (14): {rsi:.2f}
Günlük VIX (Korku Endeksi): {vix:.2f}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" },
            temperature=0.3
        )
        import json
        ans = json.loads(response.choices[0].message.content)
        return ans.get("decision", "RED") == "ONAYLA"
    except Exception as e:
        print(f"API Hatası: {e}")
        return False

def run_ai_backtest(ticker_symbol="PLTR"):
    print(f"\n--- {ticker_symbol} SCALPING BACKTEST (AI FİLTRELİ) ---")
    
    # 1. Günlük Verileri Çek (1 Yıllık, EMA 200 hesaplamak için)
    print("Veriler indiriliyor...")
    df_daily = yf.download(ticker_symbol, period="1y", interval="1d", progress=False)
    if df_daily.empty:
        print("Günlük veri alınamadı.")
        return
    if isinstance(df_daily.columns, pd.MultiIndex):
        df_daily.columns = df_daily.columns.droplevel(1)
        
    df_daily['EMA_200'] = ta.ema(df_daily['Close'].squeeze(), length=200)
    
    # VIX Verisi Çek
    df_vix = yf.download("^VIX", period="1y", interval="1d", progress=False)
    if isinstance(df_vix.columns, pd.MultiIndex):
        df_vix.columns = df_vix.columns.droplevel(1)
        
    # 2. 5 Dakikalık Verileri Çek (Son 1 Ay)
    df_5m = yf.download(ticker_symbol, period="1mo", interval="5m", progress=False)
    if df_5m.empty:
        print("5m veri alınamadı.")
        return
    if isinstance(df_5m.columns, pd.MultiIndex):
        df_5m.columns = df_5m.columns.droplevel(1)

    # Timezone hizalaması
    for df in [df_daily, df_vix, df_5m]:
        if df.index.tz is None:
            df.index = df.index.tz_localize('America/New_York')
        else:
            df.index = df.index.tz_convert('America/New_York')

    # İndikatörleri ekle
    df_5m['EMA_9'] = ta.ema(df_5m['Close'].squeeze(), length=9)
    df_5m['EMA_21'] = ta.ema(df_5m['Close'].squeeze(), length=21)
    df_5m['ATR_14'] = ta.atr(df_5m['High'].squeeze(), df_5m['Low'].squeeze(), df_5m['Close'].squeeze(), length=14)
    df_5m['RSI_14'] = ta.rsi(df_5m['Close'].squeeze(), length=14)
    df_5m['VOL_SMA_20'] = ta.sma(df_5m['Volume'].squeeze(), length=20)

    initial_balance = 1000
    balance = initial_balance
    risk_per_trade = 0.01 # Max risk: Bakiyenin %1'i
    
    wins = 0
    losses = 0
    trades = []
    signals = []
    current_trade = None
    
    print("\nSon 1 ay taranıyor (AI API çağrıları sebebiyle biraz sürebilir)...\n")
    
    for i in range(21, len(df_5m)-1):
        row = df_5m.iloc[i]
        
        # Aktif işlemi yönet (Filtre kontrolünden bağımsız olarak açık işlemleri takip et)
        if current_trade:
            if current_trade['type'] == 'LONG':
                if float(row['Low']) <= current_trade['stop_loss']:
                    balance -= current_trade['risk_amount']
                    losses += 1
                    current_trade = None
                elif float(row['High']) >= current_trade['take_profit']:
                    balance += current_trade['reward_amount']
                    wins += 1
                    current_trade = None
            elif current_trade['type'] == 'SHORT':
                if float(row['High']) >= current_trade['stop_loss']:
                    balance -= current_trade['risk_amount']
                    losses += 1
                    current_trade = None
                elif float(row['Low']) <= current_trade['take_profit']:
                    balance += current_trade['reward_amount']
                    wins += 1
                    current_trade = None
            continue

        # Tarihlere göre günlük eşleşmeleri yap
        date_val = row.name.date()
        past_daily = df_daily[df_daily.index.date <= date_val]
        past_vix = df_vix[df_vix.index.date <= date_val]
        
        if len(past_daily) == 0 or len(past_vix) == 0:
            continue
            
        daily_ema_200 = float(past_daily['EMA_200'].iloc[-1])
        daily_close = float(past_daily['Close'].iloc[-1])
        daily_trend = "BULLISH" if daily_close > daily_ema_200 else "BEARISH"
        vix_val = float(past_vix['Close'].iloc[-1])
        
        # VIX 25 üzeri ise işleme girme
        if vix_val > 25:
            continue
            
        # Hacim Filtresi (Gerçek hacim, SMA 20'nin 1.5 katı mı?)
        vol_sma = float(df_5m['VOL_SMA_20'].iloc[i])
        current_vol = float(row['Volume'])
        if current_vol < (vol_sma * 1.5):
            continue
        
        atr = float(df_5m['ATR_14'].iloc[i])
        rsi = float(df_5m['RSI_14'].iloc[i])
        if pd.isna(atr): atr = float(row['Close']) * 0.005

        ema9 = float(df_5m['EMA_9'].iloc[i])
        ema21 = float(df_5m['EMA_21'].iloc[i])
        ema9_prev = float(df_5m['EMA_9'].iloc[i-1])
        ema21_prev = float(df_5m['EMA_21'].iloc[i-1])
        
        potential_action = None
        
        # Sinyal Kurulumu
        if ema9 > ema21 and ema9_prev <= ema21_prev:
            potential_action = "LONG"
        elif ema9 < ema21 and ema9_prev >= ema21_prev:
            potential_action = "SHORT"
            
        if potential_action:
            signals.append(potential_action)
            # AI ONAYI İSTE
            is_approved = check_ai_approval(potential_action, daily_trend, rsi, vix_val)
            print(f"{date_val} {row.name.time()}: Sinyal={potential_action}, Trend={daily_trend}, RSI={rsi:.1f}, Vol Spike={current_vol/vol_sma:.1f}x -> AI: {'ONAYLANDI' if is_approved else 'REDDEDİLDİ'}")
            
            if is_approved:
                entry_price = float(df_5m['Close'].iloc[i])
                
                # Risk = Bakiyenin %1'i
                risk_amount = balance * risk_per_trade
                reward_amount = risk_amount * 2 # 1:2 R/R
                
                if potential_action == "LONG":
                    stop_loss = entry_price - (atr * 1.5)
                    take_profit = entry_price + (atr * 3.0)
                else:
                    stop_loss = entry_price + (atr * 1.5)
                    take_profit = entry_price - (atr * 3.0)
                
                current_trade = {
                    'type': potential_action,
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'risk_amount': risk_amount,
                    'reward_amount': reward_amount
                }
                trades.append(current_trade)

    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    profit_pct = ((balance - initial_balance) / initial_balance) * 100
    
    print("\n--------------------------------------------------")
    print(f"Hisse: {ticker_symbol} | Süre: Son 1 Ay | EMA200 + VIX + Vol SMA + AI Onayı")
    print(f"Oluşan Toplam Teknik Sinyal (Vol Spike dahil): {len(signals)}")
    print(f"AI Tarafından Onaylanıp Girilen İşlem: {total_trades}")
    print(f"Başlangıç Bakiyesi: ${initial_balance:.2f}")
    print(f"Bitiş Bakiyesi:     ${balance:.2f} (%{profit_pct:.2f} PnL)")
    print(f"Kazanılan/Kaybedilen:{wins} W / {losses} L")
    print(f"Kazanma Oranı (Win Rate): %{win_rate:.2f}")
    print("--------------------------------------------------")

if __name__ == "__main__":
    run_ai_backtest("PLTR")
