import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pymysql
import redis
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

def snapshot_kpis():
    conn = connect_db()
    cur = conn.cursor()
    period = datetime.now().strftime('%Y-%W')
    metrics = {
        "total_prospects": "SELECT COUNT(*) FROM prospects",
        "emails_valides": "SELECT COUNT(*) FROM prospects WHERE email_valide = 1",
        "campagnes_actives": "SELECT COUNT(*) FROM campagnes WHERE statut = 'en_cours'",
        "posts_publies": "SELECT COUNT(*) FROM posts_sociaux WHERE statut = 'publié'",
        "prospects_contactes": "SELECT COUNT(*) FROM prospects WHERE statut = 'contacté'",
    }
    for metric_name, query in metrics.items():
        cur.execute(query)
        value = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO analytics_snapshots (metric_name, value, period) VALUES (%s, %s, %s)",
            (metric_name, value, period)
        )
    conn.commit()
    conn.close()
    print(f"[Analytics Agent] Snapshot enregistré — période {period}")

def process_task(task_id, payload):
    snapshot_kpis()
    r.set(f"task:{task_id}:result", json.dumps({"status": "done"}))

def run():
    init_group()
    print("Analytics Agent démarré...")
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
                    except Exception as e: print(f"Erreur analytics: {e}")

if __name__ == "__main__":
    run()