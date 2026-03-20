import redis
from app.core.config import REDIS_HOST, MAX_ATTEMPTS

r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)


def check_attempts(key: str):
    attempts = int(r.get(f"attempts:{key}") or 0)
    if attempts >= MAX_ATTEMPTS:
        raise Exception("Too many attempts")


def increment_attempts(key: str):
    r.incr(f"attempts:{key}")
    r.expire(f"attempts:{key}", 300)


def reset_attempts(key: str):
    r.delete(f"attempts:{key}")

