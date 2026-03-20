import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import DATABASE_URL

logger = logging.getLogger(__name__)

MAX_RETRIES = 10
RETRY_DELAY = 2

Base = declarative_base()

engine = None
for attempt in range(MAX_RETRIES):
    try:
        candidate = create_engine(DATABASE_URL, future=True)
        with candidate.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine = candidate
        logger.info("Database connected successfully")
        print("✅ Database connected", flush=True)
        break
    except OperationalError as e:
        logger.warning(
            "DB not ready, retry %s/%s: %s", attempt + 1, MAX_RETRIES, e
        )
        print(
            f"⏳ DB not ready, retry {attempt + 1}/{MAX_RETRIES}",
            flush=True,
        )
        time.sleep(RETRY_DELAY)
    except Exception as e:
        logger.warning(
            "DB connection failed, retry %s/%s: %s", attempt + 1, MAX_RETRIES, e
        )
        print(
            f"⏳ DB not ready, retry {attempt + 1}/{MAX_RETRIES}",
            flush=True,
        )
        time.sleep(RETRY_DELAY)

if engine is None:
    raise RuntimeError("❌ Could not connect to database after all retries")

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, future=True
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db_schema() -> None:
    """Create tables only after DB is reachable (engine already verified at import)."""
    from app.models.client import Client  # noqa: F401

    Base.metadata.create_all(bind=engine)
