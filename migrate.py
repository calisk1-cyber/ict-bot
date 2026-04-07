from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
import sys

# Windows console encoding fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except: pass

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

migrations = [
    "ALTER TABLE live_trades ADD COLUMN IF NOT EXISTS lot_size FLOAT DEFAULT 0.01",
    "ALTER TABLE live_trades ADD COLUMN IF NOT EXISTS sl_pips FLOAT DEFAULT 0.0",
    "ALTER TABLE live_trades ADD COLUMN IF NOT EXISTS outcome VARCHAR DEFAULT NULL",
    "ALTER TABLE live_trades ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'OPEN'",
]

with engine.connect() as conn:
    print("--- Veritabanı Migrasyonu Başlatılıyor ---")
    for sql in migrations:
        try:
            conn.execute(text(sql))
            print(f"[OK] {sql[:55]}...")
        except Exception as e:
            print(f"[HATA] {sql[:30]}... -> {e}")
    conn.commit()
    print("\n[TAMAM] Migration Başarıyla Tamamlandı!")