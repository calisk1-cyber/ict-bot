import redis
import os
from dotenv import load_dotenv

load_dotenv()
REDIS_URL = os.getenv("REDIS_URL")
r = redis.from_url(REDIS_URL)

pending = r.llen("strategies:pending")
tested = r.llen("strategies:tested")
passed = r.scard("strategies:passed")
total = r.scard("memo:github_repos")

print(f"--- REDIS STATUS (Gen 2) ---")
print(f"Repos Found: {total}")
print(f"Pending Backtest: {pending}")
print(f"Tested (In Evaluator): {tested}")
print(f"Passed Professional Audit: {passed}")
