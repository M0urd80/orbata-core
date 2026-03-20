import os

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
OTP_TTL = 300
MAX_ATTEMPTS = 5
RATE_LIMIT = 5  # per minute
SECRET_KEY = "f6a3dad5-9f58-454e-87e1-a2a38b49984d"

