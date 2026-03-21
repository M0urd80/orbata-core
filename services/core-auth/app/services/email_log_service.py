import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.email_log import EmailLog
from app.services.otp_service import publish_otp_event


def create_pending_log_and_enqueue(
    db: Session,
    *,
    recipient_email: str,
    client_id: str,
    otp: str,
    client_name: str,
) -> str:
    """
    Insert EmailLog (pending, attempts=0) BEFORE Redis enqueue; payload includes log_id.
    Rolls back if enqueue fails so we do not leave pending rows without jobs.
    """
    log = EmailLog(
        client_id=uuid.UUID(client_id),
        email=recipient_email,
        status="pending",
        attempts=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(log)
    try:
        db.flush()
        log_id = str(log.id)
        publish_otp_event(
            recipient_email,
            otp,
            client_name,
            client_id,
            log_id=log_id,
        )
        db.commit()
        db.refresh(log)
        return log_id
    except Exception:
        db.rollback()
        raise
