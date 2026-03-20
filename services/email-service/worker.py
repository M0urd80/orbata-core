import json
import logging
import os
import random
import smtplib
import time
from email.mime.text import MIMEText

import redis

r = redis.Redis(host="redis", port=6379, decode_responses=True)

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_LOGIN = os.getenv("SMTP_LOGIN")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL")

smtp_conn = None

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


def get_smtp_connection():
    global smtp_conn

    if smtp_conn is None:
        smtp_conn = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        smtp_conn.starttls()
        smtp_conn.login(SMTP_LOGIN, SMTP_PASSWORD)
        log_event("smtp_connected", status="success")

    return smtp_conn


def send_email(to_email, otp):
    global smtp_conn

    msg = MIMEText(f"Your OTP code is: {otp}")
    msg["Subject"] = "Your verification code"
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email

    try:
        conn = get_smtp_connection()
        conn.send_message(msg)
    except Exception:
        log_event("smtp_failed_reconnecting", email=to_email, status="retry")
        smtp_conn = None
        conn = get_smtp_connection()
        conn.send_message(msg)


def schedule_retry(job):
    job["attempt"] += 1

    delay = (2 ** job["attempt"]) + random.randint(0, 2)
    job["next_try_at"] = int(time.time()) + delay

    log_event(
        "retry_scheduled",
        email=job.get("email", ""),
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
    try:
        log_event(
            "email_processing",
            email=job.get("email", ""),
            status="processing",
            attempt=job.get("attempt", 0),
        )
        send_email(job["email"], job["otp"])
        log_event(
            "email_sent",
            email=job.get("email", ""),
            status="success",
            attempt=job.get("attempt", 0),
        )
    except Exception as e:
        log_event(
            "email_failed",
            email=job.get("email", ""),
            status="failed",
            attempt=job.get("attempt", 0),
            error=str(e),
        )
        if job["attempt"] < job["max_attempts"]:
            schedule_retry(job)
        else:
            move_to_dlq(job, e)


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
