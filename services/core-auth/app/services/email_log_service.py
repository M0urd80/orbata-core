import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.email_log import EmailLog
from app.services.otp_service import publish_otp_event, publish_phone_otp_event


def create_pending_log_and_enqueue(
    db: Session,
    *,
    recipient_email: str,
    client_id: str,
    otp: str,
    client_name: str,
    service_id: str,
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
            service_id=service_id,
        )
        db.commit()
        db.refresh(log)
        return log_id
    except Exception:
        db.rollback()
        raise


def create_pending_sms_log_and_enqueue(
    db: Session,
    *,
    recipient_phone: str,
    client_id: str,
    message: str,
    client_name: str,
    service_id: str,
    queue_to: str | None = None,
    queue_channel: str = "sms",
) -> str:
    """
    Pending ``email_logs`` row then Redis job. ``recipient_phone`` is stored in ``email`` column
    (E.164 or ``whatsapp:+...``). ``queue_to`` defaults to ``recipient_phone`` for the job payload.
    """
    log = EmailLog(
        client_id=uuid.UUID(client_id),
        email=recipient_phone,
        status="pending",
        attempts=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(log)
    try:
        db.flush()
        log_id = str(log.id)
        publish_phone_otp_event(
            to=queue_to or recipient_phone,
            message=message,
            client_name=client_name,
            client_id=client_id,
            log_id=log_id,
            service_id=service_id,
            channel=queue_channel,
        )
        db.commit()
        db.refresh(log)
        return log_id
    except Exception:
        db.rollback()
        raise
