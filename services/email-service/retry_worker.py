import redis
import json
import time

r = redis.Redis(host="redis", port=6379, decode_responses=True)

print("🔁 Retry worker started...", flush=True)

while True:
    now = int(time.time())
    jobs = r.zrangebyscore("email_retry_zset", 0, now)

    for job in jobs:
        print("🔄 Requeueing job", flush=True)
        r.lpush("email_queue", job)
        r.zrem("email_retry_zset", job)

    time.sleep(1)
