import os
import redis
import json
import uuid

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

STREAM_KEY = "agent_tasks"

def send_task(agent_type: str, payload: dict) -> str:
    task_id = str(uuid.uuid4())
    r.xadd(STREAM_KEY, {
        "task_id": task_id,
        "agent_type": agent_type,
        "payload": json.dumps(payload)
    })
    return task_id