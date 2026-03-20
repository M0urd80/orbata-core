import redis
from datetime import datetime

from fastapi import HTTPException

from app.core.config import CLIENT_RATE_LIMIT, REDIS_HOST

r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

LIMIT = CLIENT_RATE_LIMIT


def check_rate_limit(client_id: str) -> None:
    now = datetime.utcnow().strftime("%Y-%m-%d-%H-%M")
    key = f"rate:{client_id}:{now}"

    count = r.incr(key)

    if count == 1:
        r.expire(key, 60)

    if count > LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
        )
