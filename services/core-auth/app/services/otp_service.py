import random
import json
import redis
from app.core.config import OTP_TTL
from app.core.security import hash_otp

r = redis.Redis(host="redis", port=6379, decode_responses=True)


def generate_otp():
    return str(random.randint(100000, 999999))


def acquire_otp_lock(identifier: str, ttl: int = 60) -> bool:
    return bool(r.set(f"otp:lock:{identifier}", "1", ex=ttl, nx=True))


def store_otp(identifier: str, otp: str):
    hashed = hash_otp(otp)
    r.setex(f"otp:{identifier}", OTP_TTL, hashed)


def publish_otp_event(email: str, otp: str, client_name: str, client_id: str):
    event = {
        "type": "OTP",
        "email": email,
        "otp": otp,
        "client_id": client_id,
        "client_name": client_name,
        "attempt": 0,
        "max_attempts": 3,
        "next_try_at": 0,
    }
    r.lpush("email_queue", json.dumps(event))
    print("📤 Event pushed to queue")

