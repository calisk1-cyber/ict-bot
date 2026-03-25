import pandas as pd
import json
import os
from openai import OpenAI
from datetime import datetime

# Config
LOG_FILE = "ict_trade_history.csv"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def run_daily_optimization():
    print("🧠 AI Strateji Optimizasyonu Başlatılıyor...")
    
    if not os.path.exists(LOG_FILE):
        print("❌ Hata: İşlem geçmişi bulunamadı.")
        return

    # 1. Veriyi Oku (Son 30 kayıt)
    try:
        df = pd.read_csv(LOG_FILE)
        last_trades = df.tail(30).to_string()
    except Exception as e:
        print(f"❌ Veri okuma hatası: {e}")
        return

    # 2. OpenAI Analizi
    prompt = f"""
    Aşağıda ICT Trading Bot'unun son 30 işlem denemesi (sinyalleri ve sonuçları) yer almaktadır:
    
    {last_trades}
    
    ANALİZ İSTEĞİ:
    1. Hangi rejimde (TRENDING/CHOPPY) bot daha başarılı?
    2. Hangi pariteler (ticker) daha çok 'AI_REJECTED' alıyor? Neden?
    3. Yarın için 'min_threshold' (skor eşiği) veya 'risk' ayarlarında bir değişiklik önerir misin?
    
    Lütfen profesyonel bir fon yöneticisi gibi Türkçe özet ve teknik tavsiyeler ver.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Sen dünyanın en kıdemli ICT stratejistisin. Görevin bot verilerini analiz edip karlılığı artırmaktır."},
                {"role": "user", "content": prompt}
            ]
        )
        
        analysis = response.choices[0].message.content
        print("\n--- 📊 AI STRATEJİ RAPORU ---")
        print(analysis)
        
        # Raporu kaydet
        report_file = f"ai_report_{datetime.now().strftime('%Y%m%d')}.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(f"# ICT Bot Günü Özeti - {datetime.now().strftime('%Y-%m-%d')}\n\n")
            f.write(analysis)
        print(f"\n✅ Rapor oluşturuldu: {report_file}")
        
    except Exception as e:
        print(f"❌ AI Analiz hatası: {e}")

if __name__ == "__main__":
    run_daily_optimization()
