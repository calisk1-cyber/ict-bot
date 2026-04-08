import os
import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db_models import Strategy
import json

from dotenv import load_dotenv
load_dotenv()

# DB & Redis Setup from Environment
db_url = os.getenv("DATABASE_URL")
redis_url = os.getenv("REDIS_URL")

engine = create_engine(db_url)
Session = sessionmaker(bind=engine)
r = redis.Redis.from_url(redis_url, decode_responses=True)

def reset_and_requeue():
    print("--- [MAINTENANCE] Resetting Strategy Memory ---")
    
    # 1. Clear Redis Memory (Deduplication Sets)
    r.delete("memo:backtested_strats")
    r.delete("memo:evaluated_strats")
    print("Cleared: memory for backtests and evaluations.")
    
    # 2. Get all strategies from DB
    session = Session()
    strategies = session.query(Strategy).all()
    print(f"Found {len(strategies)} strategies in database.")
    
    # 3. Push to Queue
    for s in strategies:
        strat_data = {
            "strategy_id": s.id,
            "name": s.name,
            "timeframes": s.timeframes,
            "pairs": s.pairs,
            "entry_logic": s.entry_logic,
            "exit_logic": s.exit_logic
        }
        r.lpush("strategies:pending", json.dumps(strat_data))
    
    print(f"Successfully re-queued {len(strategies)} strategies for PROFESSIONAL AUDIT.")
    session.close()

if __name__ == "__main__":
    reset_and_requeue()
