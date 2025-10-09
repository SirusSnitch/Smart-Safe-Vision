import redis
from celery import Celery

# -------------------------------
# Configure Redis and Celery
# -------------------------------
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
app = Celery("smartVision", broker=BROKER_URL)

redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

# -------------------------------
# 1️⃣ Clear all camera-related keys
# -------------------------------
keys_to_delete = []
for pattern in ["camera:*:streaming", "camera:*:frame"]:
    keys = redis_client.keys(pattern)
    keys_to_delete.extend(keys)
    if keys:
        redis_client.delete(*keys)

print(f"✅ Cleared {len(keys_to_delete)} camera keys from Redis")

# -------------------------------
# 2️⃣ Revoke any pending Celery tasks for old cameras
# -------------------------------
i = 0
for task_id in app.control.inspect().reserved().values():
    for task in task_id:
        if "camera" in task["name"]:
            app.control.revoke(task["id"], terminate=True)
            i += 1

print(f"✅ Revoked {i} lingering camera tasks in Celery")
