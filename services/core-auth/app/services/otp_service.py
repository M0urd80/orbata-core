import random
import json
import redis
from app.core.config import OTP_TTL
from app.core.security import hash_otp

r = redis.Redis(host="redis", port=6379, decode_responses=True)


def generate_otp():
    return str(random.randint(100000, 999999))


def store_otp(identifier: str, otp: str):
    hashed = hash_otp(otp)
    r.setex(f"otp:{identifier}", OTP_TTL, hashed)


def publish_otp_event(email: str, otp: str):
    event = {
        "type": "OTP",
        "email": email,
        "otp": otp,
    }
    r.lpush("email_queue", json.dumps(event))
    print("📤 Event pushed to queue")

