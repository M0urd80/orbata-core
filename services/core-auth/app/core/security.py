import hashlib
from app.core.config import SECRET_KEY


def hash_otp(otp: str) -> str:
    return hashlib.sha256((otp + SECRET_KEY).encode()).hexdigest()

