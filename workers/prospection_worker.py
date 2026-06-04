import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import redis
from dotenv import load_dotenv

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
    query = payload.get("query", "hôtels Marrakech")
    max_results = payload.get("max_results", 20)
    result = {
        "leads_found": max_results,
        "query": query,
        "sample": [{"name": "Hôtel Example", "email": "contact@example.com"}]
    }
    r.set(f"task:{task_id}:result", json.dumps(result))
    print(f"[Prospection Worker] Recherche : {query}")
    return result

def run():
    init_group()
    print("Prospection Worker démarré...")
    while True:
        results = r.xreadgroup(GROUP_NAME, "prospection_worker", {STREAM_KEY: '>'}, count=1, block=5000)
        if not results: continue
        for stream, messages in results:
            for msg_id, data in messages:
                if data.get("agent_type") == "prospection":
                    r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    task_id = data["task_id"]
                    payload = json.loads(data["payload"])
                    try: process_task(task_id, payload)
                    except Exception as e: print(f"Erreur: {e}")

if __name__ == "__main__":
    run()