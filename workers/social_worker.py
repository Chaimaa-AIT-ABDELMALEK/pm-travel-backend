import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import redis
from dotenv import load_dotenv
from social.social_service import generer_post_complet

load_dotenv()

r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=True)
STREAM_KEY = "agent_tasks"
GROUP_NAME = "agents_group"

def init_group():
    try:
        r.xgroup_create(STREAM_KEY, GROUP_NAME, id='0', mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e): raise

def process_task(task_id, payload):
    plateforme = payload.get("plateforme", "instagram")
    theme = payload.get("theme", "voyage")
    langue = payload.get("langue", "français")
    post = generer_post_complet(plateforme, theme, langue)
    result = {"plateforme": plateforme, "post": post, "status": "generated"}
    r.set(f"task:{task_id}:result", json.dumps(result))
    print(f"[Social Worker] Post {plateforme}/{theme} généré")
    return result

def run():
    init_group()
    print("Social Worker démarré...")
    while True:
        results = r.xreadgroup(GROUP_NAME, "social_worker", {STREAM_KEY: '>'}, count=1, block=5000)
        if not results: continue
        for stream, messages in results:
            for msg_id, data in messages:
                if data.get("agent_type") == "social":
                    r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    task_id = data["task_id"]
                    payload = json.loads(data["payload"])
                    try: process_task(task_id, payload)
                    except Exception as e: print(f"Erreur: {e}")

if __name__ == "__main__":
    run()