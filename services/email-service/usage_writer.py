import logging
import uuid

from sqlalchemy import select, update

from db_session import SessionLocal
from usage_model import Service, Usage, utc_today

logger = logging.getLogger("email-worker")

SERVICE_NAME_EMAIL = "email"


def _resolve_service_id(db, service_id_str: str | None) -> uuid.UUID | None:
    """Prefer queue payload `service_id`; else lookup `services.name = email` (legacy jobs)."""
    if service_id_str:
        try:
            return uuid.UUID(str(service_id_str))
        except (ValueError, TypeError):
            logger.warning("Invalid service_id in job, falling back to '%s'", SERVICE_NAME_EMAIL)
    row = (
        db.execute(select(Service).where(Service.name == SERVICE_NAME_EMAIL))
        .scalars()
        .first()
    )
    return row.id if row else None


def record_email_delivery(
    client_id: str | None, success: bool, service_id: str | None = None
) -> None:
    """
    After an SMTP attempt: bump success_count or fail_count for
    (client_id, UTC date, service_id). Row should exist from /otp/send sent_count upsert.
    """
    if not client_id:
        return
    try:
        cid = uuid.UUID(str(client_id))
    except (ValueError, TypeError):
        logger.warning("Invalid client_id for usage update, skipping")
        return

    today = utc_today()
    db = SessionLocal()
    try:
        sid = _resolve_service_id(db, service_id)
        if sid is None:
            logger.warning("Could not resolve service_id for usage update, skipping")
            return

        if success:
            stmt = (
                update(Usage)
                .where(
                    Usage.client_id == cid,
                    Usage.date == today,
                    Usage.service_id == sid,
                )
                .values(success_count=Usage.success_count + 1)
            )
        else:
            stmt = (
                update(Usage)
                .where(
                    Usage.client_id == cid,
                    Usage.date == today,
                    Usage.service_id == sid,
                )
                .values(fail_count=Usage.fail_count + 1)
            )
        result = db.execute(stmt)
        if result.rowcount:
            db.commit()
            return

        db.add(
            Usage(
                client_id=cid,
                date=today,
                service_id=sid,
                sent_count=0,
                success_count=1 if success else 0,
                fail_count=0 if success else 1,
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to update usage for client_id=%s: %s", client_id, e)
    finally:
        db.close()
