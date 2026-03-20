import redis
from fastapi import HTTPException
from app.core.config import REDIS_HOST
from app.core.security import hash_otp
from app.services.attempt_service import (
    check_attempts,
    increment_attempts,
    reset_attempts,
)

r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)


def verify_otp(identifier: str, otp: str) -> bool:
    check_attempts(identifier)

    stored = r.get(f"otp:{identifier}")
    if not stored:
        return False

    if stored == hash_otp(otp):
        r.delete(f"otp:{identifier}")
        reset_attempts(identifier)
        return True

    increment_attempts(identifier)

    attempts = int(r.get(f"attempts:{identifier}") or 0)
    if attempts >= 5:
        raise HTTPException(status_code=429, detail="Too many attempts")

    return False

