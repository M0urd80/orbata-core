import redis
from datetime import datetime

from app.core.config import REDIS_HOST

r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)


def increment_usage(client_id: str) -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    key = f"usage:{client_id}:{today}"

    r.incr(key)
    r.expire(key, 60 * 60 * 24 * 7)  # 7 days


def get_usage_today(client_id: str) -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    key = f"usage:{client_id}:{today}"
    count = r.get(key) or 0
    return {
        "client_id": client_id,
        "date": today,
        "usage": int(count),
    }
