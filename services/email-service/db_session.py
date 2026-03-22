import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _ensure_postgresql_psycopg_url(url: str) -> str:
    """Match core-auth: ``postgresql://`` → ``postgresql+psycopg://`` for SQLAlchemy + psycopg v3."""
    if not url or not isinstance(url, str):
        return url
    u = url.strip()
    if u.startswith("postgresql://") and not u.startswith("postgresql+"):
        return u.replace("postgresql://", "postgresql+psycopg://", 1)
    return u


_DEFAULT = "postgresql+psycopg://orbata:orbata@postgres:5432/orbata"
DATABASE_URL = _ensure_postgresql_psycopg_url(os.getenv("DATABASE_URL", _DEFAULT))

print(f"[DB CHECK] DATABASE_URL = {DATABASE_URL}", flush=True)

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, future=True
)
