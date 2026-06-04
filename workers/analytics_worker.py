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
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM prospects")
    total_prospects = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM campagnes")
    campagnes = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(total_envoyes),0) FROM campagnes")
    emails_envoyes = cur.fetchone()[0]
    conn.close()
    result = {
        "total_prospects": total_prospects,
        "campagnes_total": campagnes,
        "emails_envoyes": emails_envoyes,
        "timestamp": str(datetime.now())
    }
    r.set(f"task:{task_id}:result", json.dumps(result))
    print(f"[Analytics Worker] KPIs enregistrés")
    return result

def run():
    init_group()
    print("Analytics Worker démarré...")
    while True:
        results = r.xreadgroup(GROUP_NAME, "analytics_worker", {STREAM_KEY: '>'}, count=1, block=5000)
        if not results: continue
        for stream, messages in results:
            for msg_id, data in messages:
                if data.get("agent_type") == "analytics":
                    r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    task_id = data["task_id"]
                    payload = json.loads(data["payload"])
                    try: process_task(task_id, payload)
                    except Exception as e: print(f"Erreur: {e}")

if __name__ == "__main__":
    run()