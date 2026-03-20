import logging
import uuid
from typing import Optional

from db_session import SessionLocal
from email_log_model import EmailLog

logger = logging.getLogger("email-worker")


def write_email_log(
    client_id: Optional[str],
    email: str,
    status: str,
    attempts: int,
    error_message: Optional[str] = None,
) -> None:
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
