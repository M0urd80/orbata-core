import redis
import json
import time
import smtplib
import os
from email.mime.text import MIMEText

r = redis.Redis(host="redis", port=6379, decode_responses=True)

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_LOGIN = os.getenv("SMTP_LOGIN")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL")


def send_email(to_email, otp):
    msg = MIMEText(f"Your OTP code is: {otp}\nValid for 5 minutes.")
    msg["Subject"] = "Your verification code"
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_LOGIN, SMTP_PASSWORD)
        server.send_message(msg)


def schedule_retry(job):
    job["attempt"] += 1

    # exponential backoff (seconds)
    delay = 2 ** job["attempt"]
    job["next_try_at"] = int(time.time()) + delay

    print(f"🔁 Scheduling retry #{job['attempt']} in {delay}s", flush=True)

    r.lpush("email_retry_queue", json.dumps(job))


def move_to_dlq(job):
    print("💀 Moving to DLQ:", job, flush=True)
    r.lpush("email_dlq", json.dumps(job))


def process_job(job):
    try:
        print(f"📨 Sending OTP to {job['email']}", flush=True)
        send_email(job["email"], job["otp"])
        print("✅ Email sent", flush=True)

    except Exception as e:
        print(f"❌ Failed: {e}", flush=True)

        if job["attempt"] < job["max_attempts"]:
            schedule_retry(job)
        else:
            move_to_dlq(job)


print("📧 Email worker started...", flush=True)

while True:
    job = r.brpop("email_queue", timeout=2)

    if job:
        data = json.loads(job[1])
        process_job(data)
