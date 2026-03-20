import random
import redis
from app.core.config import REDIS_HOST, OTP_TTL
from app.core.security import hash_otp

r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)


def generate_otp():
    return str(random.randint(100000, 999999))


def store_otp(identifier: str, otp: str):
    hashed = hash_otp(otp)
    r.setex(f"otp:{identifier}", OTP_TTL, hashed)

