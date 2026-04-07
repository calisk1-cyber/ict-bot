import os
import redis
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Load environment variables from absolute path
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"), override=True)

class BaseAgent:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.setup_logging()
        
        # Redis Setup
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        try:
            self.redis_client = redis.StrictRedis.from_url(
                self.redis_url, 
                decode_responses=True,
                socket_timeout=15.0,
                socket_connect_timeout=15.0
            )
            self.redis_client.ping()
            self.logger.info(f"[{agent_name}] Connected to Redis at {self.redis_url}")
        except Exception as e:
            self.logger.warning(f"[{agent_name}] Redis connectivity issue: {e}")
            self.redis_client = None

        # DB Setup
        self.db_url = os.getenv("DATABASE_URL", "sqlite:///ict_bot.db")
        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)
        self.logger.info(f"[{agent_name}] DB engine initialized: {self.db_url}")

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(self.agent_name)

    def push_to_queue(self, queue_name: str, data: dict):
        if self.redis_client:
            self.redis_client.rpush(queue_name, json.dumps(data))
            self.logger.debug(f"Pushed data to {queue_name}")

    def pull_from_queue(self, queue_name: str, timeout=5):
        if self.redis_client:
            # Using non-blocking lpop to avoid environment-specific blpop issues
            data = self.redis_client.lpop(queue_name)
            return json.loads(data) if data else None
        return None

    def publish(self, channel: str, message: dict):
        if self.redis_client:
            self.redis_client.publish(channel, json.dumps(message))

    def update_status(self, status: str, data: dict = None):
        """Updates the agent's status in Redis for dashboard monitoring."""
        if self.redis_client:
            payload = {
                "agent_name": self.agent_name,
                "status": status,
                "last_update": datetime.now().isoformat(),
                "data": data or {},
                "recent_logs": self.get_recent_logs()
            }
            self.redis_client.hset("bot_statuses", self.agent_name, json.dumps(payload))
            self.logger.debug(f"Status updated: {status}")

    def log_activity(self, message: str):
        """Adds a message to the bot's recent activity log in Redis."""
        if self.redis_client:
            log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
            key = f"bot_logs:{self.agent_name}"
            self.redis_client.lpush(key, log_entry)
            self.redis_client.ltrim(key, 0, 9) # Keep last 10
            self.update_status(message) # Also update main status

    def get_recent_logs(self):
        """Retrieves recent logs for this bot from Redis."""
        if self.redis_client:
            key = f"bot_logs:{self.agent_name}"
            logs = self.redis_client.lrange(key, 0, -1)
            return [l.decode('utf-8') if isinstance(l, bytes) else l for l in logs]
        return []

    def is_processed(self, memo_key: str, value: str) -> bool:
        """Checks if a value (like a URL) has already been processed using a Redis Set."""
        if self.redis_client:
            return self.redis_client.sismember(f"memo:{memo_key}", value)
        return False

    def mark_as_processed(self, memo_key: str, value: str):
        """Marks a value as processed in a Redis Set."""
        if self.redis_client:
            self.redis_client.sadd(f"memo:{memo_key}", value)

if __name__ == "__main__":
    # Test
    agent = BaseAgent("TestAgent")
    print(f"Agent {agent.agent_name} initialized.")
