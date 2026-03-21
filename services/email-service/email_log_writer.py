import logging
import uuid
from typing import Optional

from db_session import SessionLocal
from email_log_model import EmailLog

logger = logging.getLogger("email-worker")


def update_email_log(
    log_id: str,
    status: str,
    *,
    increment_attempts: bool = False,
    error_message: Optional[str] = None,
) -> None:
    """Update existing row created by core-auth (pending → success/failed)."""
    try:
        lid = uuid.UUID(log_id)
    except (ValueError, TypeError):
        logger.warning("Invalid log_id for update: %s", log_id)
        return

    db = SessionLocal()
    try:
        row = db.get(EmailLog, lid)
        if row is None:
            logger.warning("EmailLog not found for id=%s", log_id)
            return
        row.status = status
        if increment_attempts:
            row.attempts = int(row.attempts or 0) + 1
        if error_message is not None:
            row.error_message = error_message
        elif status == "success":
            row.error_message = None
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to update email_logs id=%s: %s", log_id, e)
    finally:
        db.close()


def write_email_log(
    client_id: Optional[str],
    email: str,
    status: str,
    attempts: int,
    error_message: Optional[str] = None,
) -> None:
    """Legacy: insert row when job has no log_id (old queue messages)."""
    if not client_id:
        return
    try:
        cid = uuid.UUID(client_id)
    except (ValueError, TypeError):
        logger.warning("Invalid client_id for email log, skipping DB write")
        return

    db = SessionLocal()
    try:
        row = EmailLog(
            client_id=cid,
            email=email,
            status=status,
            attempts=attempts,
            error_message=error_message,
        )
        db.add(row)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to write email_logs row: %s", e)
    finally:
        db.close()
