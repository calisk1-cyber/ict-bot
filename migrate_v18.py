import sqlite3
import os

DB_PATH = "ict_bot.db"

def migrate():
    print(f"--- [DATABASE MIGRATION V18] ---")
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found. Skipping migration (it will be created by init_database).")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Check for ai_reason
    cursor.execute("PRAGMA table_info(trades)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "ai_reason" not in columns:
        print("  --> Adding column 'ai_reason' to 'trades' table...")
        try:
            cursor.execute("ALTER TABLE trades ADD COLUMN ai_reason TEXT")
            print("  [SUCCESS] Column 'ai_reason' added.")
        except Exception as e:
            print(f"  [ERROR] Could not add column: {e}")
    else:
        print("  [OK] Column 'ai_reason' already exists.")

    # 2. Check for other potentially missing columns from newer schema
    if "red_flags" not in columns:
        print("  --> Adding column 'red_flags' to 'trades' table...")
        cursor.execute("ALTER TABLE trades ADD COLUMN red_flags TEXT")

    conn.commit()
    conn.close()
    print("--- MIGRATION COMPLETE ---")

if __name__ == "__main__":
    migrate()
