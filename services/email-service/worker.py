import redis
import json
import time
import sys

r = redis.Redis(host="redis", port=6379, decode_responses=True)

print("📧 Email worker started...", flush=True)

while True:
    print("⏳ Waiting for job...", flush=True)

    job = r.brpop("email_queue", timeout=5)

    if job:
        print("🔥 Raw job:", job, flush=True)

        data = json.loads(job[1])

        if data["type"] == "OTP":
            email = data["email"]
            otp = data["otp"]

            print(f"📨 Sending OTP {otp} to {email}", flush=True)

    else:
        time.sleep(1)
