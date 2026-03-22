import json
import logging
import random
import sys
import time

import redis
from sqlalchemy import func, select

from app.models.provider import DeliveryProvider
from app.providers.errors import ProviderError
from app.providers.routing import resolve_channel_name, send_with_failover
from db_session import SessionLocal
from email_log_writer import is_already_delivered, update_email_log, write_email_log
from usage_writer import record_email_delivery

r = redis.Redis(host="redis", port=6379, decode_responses=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("email-worker")


def log_event(event: str, email: str = "", status: str = "", attempt: int = 0, **extra):
    payload = {
        "event": event,
        "email": email,
        "status": status,
        "attempt": attempt,
    }
    payload.update(extra)
    logger.info(json.dumps(payload))


def schedule_retry(job):
    job["attempt"] = int(job.get("attempt", 0)) + 1

    delay = (2 ** job["attempt"]) + random.randint(0, 2)
    job["next_try_at"] = int(time.time()) + delay

    log_event(
        "retry_scheduled",
        email=job.get("to") or job.get("email", ""),
        status="retry",
        attempt=job["attempt"],
        delay=delay,
    )
    r.zadd("email_retry_zset", {json.dumps(job): job["next_try_at"]})


def move_to_dlq(job, error):
    job["failure_reason"] = str(error)
    job["final_attempt_at"] = int(time.time())
    job["total_attempts"] = job.get("attempt", 0)

    log_event(
        "moved_to_dlq",
        email=job.get("email", ""),
        status="failed",
        attempt=job.get("attempt", 0),
        reason=str(error),
    )
    r.lpush("email_dlq", json.dumps(job))


def process_job(job):
    """
    Email OTP → SMTP chain; SMS OTP → Twilio chain. Same retry / DLQ semantics.
    """
    log_id = job.get("log_id") or job.get("email_log_id")
    recipient = job.get("to") or job.get("email") or ""
    attempt = int(job.get("attempt", 0))
    max_attempts = int(job.get("max_attempts", 3))

    db = SessionLocal()
    try:
        logger.info(f"🔥 JOB RECEIVED: {job}")

        if log_id and is_already_delivered(log_id):
            log_event(
                "delivery_skipped_idempotent",
                email=recipient,
                status="skipped",
                attempt=attempt,
                log_id=log_id,
            )
            return

        log_event(
            "email_processing",
            email=recipient,
            status="processing",
            attempt=attempt,
        )
        client_name = job.get("client_name") or "Orbata"
        # Prefer explicit job["channel"]; if absent, resolve_channel_name (service → service_id → email).
        if "channel" in job and job["channel"] is not None and str(job["channel"]).strip():
            service = str(job["channel"]).strip().lower()
        else:
            service = resolve_channel_name(db, job)

        if service in ("sms", "whatsapp"):
            if not job.get("to") or not job.get("message"):
                raise ValueError(
                    "SMS/WhatsApp job requires non-empty 'to' and 'message'"
                )
            to_raw = str(job["to"]).strip()
            if to_raw.lower().startswith("whatsapp:"):
                to_norm = to_raw
            else:
                to_norm = to_raw.replace(" ", "").replace("-", "")
            payload = {
                "to": to_norm,
                "message": str(job["message"]),
                "channel": service,
                "service": service,
            }
        else:
            payload = {
                "to": job.get("email") or job.get("to"),
                "otp": job["otp"],
                "client_name": client_name,
                "channel": service,
                "service": service,
            }

        try:
            provider_used, routing_mode = send_with_failover(
                db, service, payload, job=job
            )
        except ProviderError as e:
            log_event(
                "email_failed",
                email=recipient,
                status="failed",
                attempt=attempt,
                error=str(e),
                retryable=True,
            )
            if log_id:
                update_email_log(
                    log_id,
                    "failed",
                    increment_attempts=True,
                    error_message=str(e),
                )
            else:
                write_email_log(
                    job.get("client_id"),
                    recipient,
                    "failed",
                    attempt,
                    error_message=str(e),
                )
            record_email_delivery(
                job.get("client_id"),
                success=False,
                service_id=job.get("service_id"),
            )
            if attempt < max_attempts:
                schedule_retry(job)
            else:
                move_to_dlq(job, e)
            return

        try:
            log_event(
                "email_sent",
                email=recipient,
                status="success",
                attempt=attempt,
                provider=provider_used,
                routing=routing_mode,
                service=service,
            )
            if log_id:
                update_email_log(log_id, "success")
            else:
                write_email_log(
                    job.get("client_id"),
                    recipient,
                    "success",
                    attempt,
                    error_message=None,
                )
            record_email_delivery(
                job.get("client_id"),
                success=True,
                service_id=job.get("service_id"),
            )
        except Exception as book_e:
            logger.error(
                "⚠️ post-delivery bookkeeping failed BUT delivery succeeded: %s",
                book_e,
            )

    except Exception as e:
        log_event(
            "email_failed",
            email=recipient,
            status="failed",
            attempt=attempt,
            error=str(e),
            retryable=False,
        )
        if log_id:
            update_email_log(
                log_id,
                "failed",
                increment_attempts=True,
                error_message=str(e),
            )
        else:
            write_email_log(
                job.get("client_id"),
                recipient,
                "failed",
                attempt,
                error_message=str(e),
            )
        record_email_delivery(
            job.get("client_id"),
            success=False,
            service_id=job.get("service_id"),
        )
        move_to_dlq(job, e)
    finally:
        db.close()


def _require_active_delivery_providers() -> None:
    """Fail fast if the registry has no active rows (routing is DB-only)."""
    db = SessionLocal()
    try:
        n = db.scalar(
            select(func.count())
            .select_from(DeliveryProvider)
            .where(DeliveryProvider.is_active.is_(True))
        )
        if not n:
            logger.critical(
                "FATAL: no active rows in email_delivery_providers — run SQL seeds "
                "(seed_sms_twilio_provider.sql, seed_whatsapp_twilio_provider.sql, "
                "seed_email_smtp_provider.sql) then restart."
            )
            sys.exit(1)
        logger.info(
            "%s",
            json.dumps(
                {
                    "event": "worker_startup_providers",
                    "active_provider_rows": int(n),
                }
            ),
        )
    finally:
        db.close()


try:
    _require_active_delivery_providers()
except Exception as e:
    logger.warning("Skipping provider check (e.g. DB or table not ready): %s", e)

log_event("worker_started", status="success")

while True:
    try:
        job = r.brpop("email_queue", timeout=2)
        if job:
            data = json.loads(job[1])
            process_job(data)
    except Exception as e:
        log_event("worker_error", status="error", error=str(e))
        time.sleep(1)
