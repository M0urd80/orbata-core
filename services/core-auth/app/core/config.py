import os

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
OTP_TTL = 300
MAX_ATTEMPTS = 5
RATE_LIMIT = 5  # per minute
CLIENT_RATE_LIMIT = int(os.getenv("CLIENT_RATE_LIMIT", "10"))
SECRET_KEY = "f6a3dad5-9f58-454e-87e1-a2a38b49984d"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "change-me-admin-secret")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "orbata")
POSTGRES_USER = os.getenv("POSTGRES_USER", "orbata")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "orbata")


def ensure_postgresql_psycopg_url(url: str) -> str:
    """
    SQLAlchemy + psycopg v3 expects ``postgresql+psycopg://``.
    Accept legacy ``postgresql://`` from env / Compose and upgrade the scheme once.
    """
    if not url or not isinstance(url, str):
        return url
    u = url.strip()
    if u.startswith("postgresql://") and not u.startswith("postgresql+"):
        return u.replace("postgresql://", "postgresql+psycopg://", 1)
    return u


_default_pg_url = (
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)
DATABASE_URL = ensure_postgresql_psycopg_url(os.getenv("DATABASE_URL", _default_pg_url))

