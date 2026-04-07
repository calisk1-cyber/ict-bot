import redis
import os
import json
from dotenv import load_dotenv

load_dotenv()
REDIS_URL = os.getenv("REDIS_URL")
r = redis.from_url(REDIS_URL)

queue_len = r.llen("strategy:active")
print(f"Active Queue Length: {queue_len}")

if queue_len == 0:
    # Manually jumpstart with a high-quality strategy
    # Mock active strategy info similar to what Bot 3 Evaluator produces
    active_info = {
        "active_strategy_id": "gen2-master-999",
        "name": "ICT Gen2 Master Suite",
        "activated_at": "2026-04-04T18:30:00",
        "score": 95.0,
        "reason": "Jumpstart: High-fidelity portfolio activation",
        "kill_conditions": { "max_loss_pct": 5, "hours": 72 }
    }
    r.rpush("strategy:active", json.dumps(active_info))
    print("SUCCESS: Pushed ICT Gen2 Master Suite to active queue.")
