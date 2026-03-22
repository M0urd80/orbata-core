import logging
import time
from typing import Set

from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import DATABASE_URL

logger = logging.getLogger(__name__)

MAX_RETRIES = 10
RETRY_DELAY = 2

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
    """
    Idempotent data fixes and seeds after Alembic has applied schema.

    Schema is created by ``alembic upgrade head`` (see Dockerfile / deploy).
    """
    _migrate_legacy_plan_quotas_to_quota_links()
    _ensure_quotas_name_and_derived_monthly()

    _seed_default_services()
    _seed_default_free_plan()
    _backfill_null_client_plans()
    _ensure_clients_plan_id_not_null_db()
    _seed_free_plan_default_quotas()


def _plan_quotas_column_names(conn) -> Set[str]:
    r = conn.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'plan_quotas'
            """
        )
    )
    return {row[0] for row in r}


def _migrate_legacy_plan_quotas_to_quota_links() -> None:
    """
    Upgrade legacy ``plan_quotas`` (plan_id + service_id + limits) to link rows
    (plan_id + quota_id) with limits on ``quotas``.
    Idempotent: no-op if ``quota_id`` exists and ``service_id`` is gone.
    """
    from app.models.quota import Quota

    try:
        with engine.connect() as conn:
            cols = _plan_quotas_column_names(conn)
        if not cols:
            return
        if "quota_id" in cols and "service_id" not in cols:
            return
        if "service_id" not in cols:
            return
    except Exception as e:
        logger.warning("plan_quotas migration inspect failed: %s", e)
        return

    db = SessionLocal()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS quotas (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        service_id UUID NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
                        name VARCHAR(255) NOT NULL DEFAULT '',
                        quota_daily INTEGER NOT NULL DEFAULT 0,
                        quota_monthly INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )

        with engine.connect() as conn:
            cols = _plan_quotas_column_names(conn)
            if "quota_id" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE plan_quotas ADD COLUMN quota_id UUID REFERENCES quotas(id)"
                    )
                )
                conn.commit()

        rows = db.execute(
            text(
                """
                SELECT id, plan_id, service_id, quota_daily, quota_monthly
                FROM plan_quotas
                WHERE quota_id IS NULL
                """
            )
        ).all()

        for row in rows:
            rid, plan_id, service_id, qd, _qm = (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
            )
            existing = db.execute(
                select(Quota).where(
                    Quota.service_id == service_id,
                    Quota.quota_daily == qd,
                )
            ).scalars().first()
            if not existing:
                existing = Quota(
                    service_id=service_id,
                    quota_daily=qd,
                )
                db.add(existing)
                db.flush()
            db.execute(
                text(
                    "UPDATE plan_quotas SET quota_id = CAST(:qid AS uuid) "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"qid": str(existing.id), "id": str(rid)},
            )
        db.commit()

        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE plan_quotas DROP CONSTRAINT IF EXISTS uq_plan_quota_plan_service_id"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE plan_quotas DROP COLUMN IF EXISTS service_id CASCADE"
                )
            )
            conn.execute(
                text("ALTER TABLE plan_quotas DROP COLUMN IF EXISTS quota_daily")
            )
            conn.execute(
                text("ALTER TABLE plan_quotas DROP COLUMN IF EXISTS quota_monthly")
            )
            conn.execute(
                text("ALTER TABLE plan_quotas ALTER COLUMN quota_id SET NOT NULL")
            )
            conn.execute(
                text(
                    """
                    DO $$ BEGIN
                        ALTER TABLE plan_quotas
                        ADD CONSTRAINT uq_plan_quota_plan_quota_id
                        UNIQUE (plan_id, quota_id);
                    EXCEPTION
                        WHEN duplicate_object THEN NULL;
                    END $$
                    """
                )
            )
        logger.info("Migrated plan_quotas to quota_id link model")
    except Exception as e:
        logger.warning("plan_quotas → quotas migration failed: %s", e)
        db.rollback()
    finally:
        db.close()


def _ensure_quotas_name_and_derived_monthly() -> None:
    """Add ``quotas.name`` if missing; set ``name`` + ``quota_monthly = daily * 30`` from services."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    ALTER TABLE quotas
                    ADD COLUMN IF NOT EXISTS name VARCHAR(255) NOT NULL DEFAULT ''
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE quotas q SET
                        quota_monthly = q.quota_daily * 30,
                        name = UPPER(s.name) || '-' || q.quota_daily::text || '/day'
                    FROM services s
                    WHERE s.id = q.service_id
                    """
                )
            )
    except Exception as e:
        logger.debug("quotas name/monthly derivative update: %s", e)


def _backfill_null_client_plans() -> None:
    """Assign ``Free`` plan to any legacy rows with ``plan_id IS NULL``."""
    from app.models.plan import Plan

    db = SessionLocal()
    try:
        free = db.execute(select(Plan).where(Plan.name == "Free")).scalars().first()
        if not free:
            return
        res = db.execute(
            text("UPDATE clients SET plan_id = CAST(:pid AS uuid) WHERE plan_id IS NULL"),
            {"pid": str(free.id)},
        )
        if res.rowcount:
            logger.info("Backfilled plan_id=Free for %s client(s)", res.rowcount)
        db.commit()
    except Exception as e:
        logger.warning("Could not backfill client plan_id: %s", e)
        db.rollback()
    finally:
        db.close()


def _ensure_clients_plan_id_not_null_db() -> None:
    """After backfill, enforce NOT NULL at DB level (PostgreSQL)."""
    try:
        with engine.begin() as conn:
            raw = conn.execute(text("SELECT COUNT(*) FROM clients WHERE plan_id IS NULL"))
            n = raw.scalar_one()
            if n > 0:
                logger.warning(
                    "%s clients still have NULL plan_id; skipping NOT NULL constraint",
                    n,
                )
                return
            conn.execute(
                text("ALTER TABLE clients ALTER COLUMN plan_id SET NOT NULL")
            )
    except Exception as e:
        logger.debug("clients.plan_id NOT NULL (optional): %s", e)


def _seed_free_plan_default_quotas() -> None:
    """
    Starter ``Quota`` rows + ``plan_quotas`` links for the Free tier (idempotent).
    """
    from app.models.plan import Plan
    from app.models.plan_quota import PlanQuota
    from app.models.quota import Quota
    from app.models.service import Service

    db = SessionLocal()
    try:
        free = db.execute(select(Plan).where(Plan.name == "Free")).scalars().first()
        if not free:
            return
        defaults = (
            ("email", 200),
            ("sms", 20),
            ("whatsapp", 20),
        )
        for svc_name, daily in defaults:
            svc = (
                db.execute(select(Service).where(Service.name == svc_name))
                .scalars()
                .first()
            )
            if not svc:
                continue
            quota = db.execute(
                select(Quota).where(
                    Quota.service_id == svc.id,
                    Quota.quota_daily == daily,
                )
            ).scalars().first()
            if not quota:
                quota = Quota(
                    service_id=svc.id,
                    quota_daily=daily,
                )
                db.add(quota)
                db.flush()
            linked = db.execute(
                select(PlanQuota).where(
                    PlanQuota.plan_id == free.id,
                    PlanQuota.quota_id == quota.id,
                )
            ).scalars().first()
            if linked:
                continue
            db.add(PlanQuota(plan_id=free.id, quota_id=quota.id))
        db.commit()
    except Exception as e:
        logger.warning("Could not seed Free plan quotas: %s", e)
        db.rollback()
    finally:
        db.close()


def _seed_default_free_plan() -> None:
    """Ensure a ``Free`` plan exists (default for new clients without ``plan_id``)."""
    from app.models.plan import Plan

    db = SessionLocal()
    try:
        exists = (
            db.execute(select(Plan).where(Plan.name == "Free")).scalars().first()
        )
        if exists:
            return
        db.add(Plan(name="Free", price=0.0))
        db.commit()
    except Exception as e:
        logger.warning("Could not seed Free plan: %s", e)
        db.rollback()
    finally:
        db.close()


def _seed_default_services() -> None:
    """Base services for ``usage`` + ``quotas``."""
    from app.models.service import Service

    defaults = [
        ("email", "OTP and transactional email"),
        ("sms", "SMS delivery"),
        ("whatsapp", "WhatsApp delivery"),
    ]
    db = SessionLocal()
    try:
        for name, description in defaults:
            exists = (
                db.execute(select(Service).where(Service.name == name))
                .scalars()
                .first()
            )
            if exists:
                continue
            db.add(Service(name=name, description=description))
        db.commit()
    except Exception as e:
        logger.warning("Could not seed default services: %s", e)
        db.rollback()
    finally:
        db.close()
