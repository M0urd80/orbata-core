import redis
import json
import time
import os
import smtplib
from email.mime.text import MIMEText

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp-relay.brevo.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_LOGIN = os.getenv("SMTP_LOGIN", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "no-reply@example.com")

print("SMTP_LOGIN:", SMTP_LOGIN, flush=True)
print("SMTP_PASSWORD:", SMTP_PASSWORD[:5] if SMTP_PASSWORD else None, flush=True)

r = redis.Redis(host="redis", port=6379, decode_responses=True)

print("📧 Email worker started...", flush=True)


def send_email(to_email, otp):
    subject = "Your verification code"
    body = f"Your OTP code is: {otp}\nValid for 5 minutes."

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email

    try:
        print("🚀 Connecting to SMTP...", flush=True)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.set_debuglevel(1)  # 🔥 VERY IMPORTANT
            server.starttls()
            server.login(SMTP_LOGIN, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"✅ Email sent to {to_email}", flush=True)

    except Exception as e:
        print(f"❌ Email failed: {e}", flush=True)

while True:
    print("⏳ Waiting for job...", flush=True)

    job = r.brpop("email_queue", timeout=5)

    if job:
        print("🔥 Raw job:", job, flush=True)

        data = json.loads(job[1])

        if data["type"] == "OTP":
            email = data["email"]
            otp = data["otp"]

            send_email(email, otp)

    else:
        time.sleep(1)
