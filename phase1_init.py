from base_agent import BaseAgent
from db_models import init_db

def main():
    print("--- Phase 1: Infrastructure Initialization ---")
    
    # 1. Initialize DB models
    agent = BaseAgent("InitAgent")
    try:
        init_db(agent.engine)
        print("[SUCCESS] Database tables created/verified.")
    except Exception as e:
        print(f"[ERROR] DB initialization failed: {e}")

    # 2. Test Redis (will likely fail or use local if not provided)
    if agent.redis_client:
        try:
            agent.redis_client.set("health_check", "ok")
            val = agent.redis_client.get("health_check")
            print(f"[SUCCESS] Redis connectivity confirmed: health_check={val}")
        except Exception as e:
            print(f"[WARNING] Redis test failed: {e}. Check REDIS_URL in .env")
    else:
        print("[WARNING] Redis client not initialized. Check .env")

if __name__ == "__main__":
    main()
