import logging
import uuid

from sqlalchemy import update

from db_session import SessionLocal
from usage_model import Usage, utc_today

logger = logging.getLogger("email-worker")

CHANNEL_EMAIL = "email"


def record_email_delivery(client_id: str | None, success: bool) -> None:
    """
    After an SMTP attempt: bump success_count or fail_count for
    (client_id, UTC date, email). Row should exist from /otp/send sent_count upsert.
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
        if success:
            stmt = (
                update(Usage)
                .where(
                    Usage.client_id == cid,
                    Usage.date == today,
                    Usage.channel == CHANNEL_EMAIL,
                )
                .values(success_count=Usage.success_count + 1)
            )
        else:
            stmt = (
                update(Usage)
                .where(
                    Usage.client_id == cid,
                    Usage.date == today,
                    Usage.channel == CHANNEL_EMAIL,
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
                channel=CHANNEL_EMAIL,
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
