import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import redis
import pymysql
from datetime import datetime
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

def connect_db():
    return pymysql.connect(
        host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT')),
        user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'), charset='utf8mb4'
    )

def process_task(task_id, payload):
    text = payload.get("text", "")
    violations = []
    if "email" in text.lower() and "consentement" not in text.lower():
        violations.append("Absence de mention de consentement")
    forbidden = ["gratuit", "urgent", "offre spéciale"]
    for word in forbidden:
        if word in text.lower():
            violations.append(f"Mot sensible détecté: {word}")
    result = {"compliant": len(violations) == 0, "violations": violations}
    r.set(f"task:{task_id}:result", json.dumps(result))
    print(f"[Compliance Worker] {'Conforme' if result['compliant'] else 'Non conforme'}")
    return result

def run():
    init_group()
    print("Compliance Worker démarré...")
    while True:
        results = r.xreadgroup(GROUP_NAME, "compliance_worker", {STREAM_KEY: '>'}, count=1, block=5000)
        if not results: continue
        for stream, messages in results:
            for msg_id, data in messages:
                if data.get("agent_type") == "compliance":
                    r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    task_id = data["task_id"]
                    payload = json.loads(data["payload"])
                    try: process_task(task_id, payload)
                    except Exception as e: print(f"Erreur: {e}")

if __name__ == "__main__":
    run()