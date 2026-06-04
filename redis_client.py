import redis
import os
import uuid
import json
from dotenv import load_dotenv

load_dotenv()

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    decode_responses=True
)

STREAM_KEY = "agent_tasks"
GROUP_NAME = "agents_group"

def init_group():
    try:
        r.xgroup_create(STREAM_KEY, GROUP_NAME, id='0', mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

def send_task(agent_type: str, payload: dict) -> str:
    task_id = str(uuid.uuid4())
    r.xadd(STREAM_KEY, {
        "task_id": task_id,
        "agent_type": agent_type,
        "payload": json.dumps(payload)
    })
    return task_id