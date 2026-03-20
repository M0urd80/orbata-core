import redis
from app.core.config import REDIS_HOST, RATE_LIMIT

r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)


def check_rate_limit(key: str):
    redis_key = f"rate:{key}"
    count = r.incr(redis_key)

    if count == 1:
        r.expire(redis_key, 60)

    if count > RATE_LIMIT:
        raise Exception("Rate limit exceeded")

