import pandas as pd
import json
import os
from openai import OpenAI
from datetime import datetime

# Config
LOG_FILE = "ict_trade_history.csv"
KNOWLEDGE_FILE = "ict_knowledge_base.json"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def run_daily_optimization():
    print("🧠 AI Strateji Denetimi ve Öğrenme Süreci Başlatılıyor...")
    
    if not os.path.exists(LOG_FILE):
        print("❌ Hata: İşlem geçmişi bulunamadı.")
        return

    # 1. Verileri Oku
    try:
        df_history = pd.read_csv(LOG_FILE).tail(20)
        kb_data = {}
        if os.path.exists(KNOWLEDGE_FILE):
            with open(KNOWLEDGE_FILE, 'r') as f:
                kb_data = json.load(f)
        
        # Sadece son snapshotları özetle
        kb_summary = {k: v[-5:] for k, v in kb_data.items()}
    except Exception as e:
        print(f"❌ Veri okuma hatası: {e}")
        return

    # 2. OpenAI Analizi (Deep Learning Audit)
    prompt = f"""
    Aşağıda ICT Bot'unun son işlemleri ve bu işlemler anındaki teknik hafıza (Market Snapshots) yer almaktadır:
    
    İŞLEM GEÇMİŞİ:
    {df_history.to_string()}
    
    TEKNİK HAFIZA (SNAPSHOTS):
    {json.dumps(kb_summary, indent=2)}
    
    STRATEJİK DENETİM İSTEĞİ:
    1. Geçmiş işlemlerdeki ortak hata paternlerini bul (Örn: "Düşük Efficiency Ratio'da hep stop olunmuş").
    2. Mevcut puanlama ağırlıklarını (Silver Bullet, FVG, SMT vb.) optimize etmek için yeni değerler öner.
    3. Hangi rejimlerde (CHOP/TREND) botun 'IQ'su düşüyor?
    
    Lütfen teknik bir rapor ver ve STRATEGY_WEIGHTS sözlüğü için JSON formatında yeni önerilerini ekle.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Sen dünyanın en gelişmiş algoritmik ICT denetçisisin. Verilerden öğrenip sistemi optimize edersin."},
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
