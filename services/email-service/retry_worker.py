import redis
import json
import time

r = redis.Redis(host="redis", port=6379, decode_responses=True)

print("🔁 Retry worker started...", flush=True)

while True:
    job = r.brpop("email_retry_queue", timeout=5)

    if job:
        data = json.loads(job[1])

        if int(time.time()) >= data["next_try_at"]:
            print("🔄 Requeueing job", flush=True)
            r.lpush("email_queue", json.dumps(data))
        else:
            # not ready -> push back
            r.lpush("email_retry_queue", json.dumps(data))
            time.sleep(1)
