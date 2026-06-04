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

def verifier_prospect(prospect_id):
    conn = connect_db()
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM prospects WHERE id = %s", (prospect_id,))
    prospect = cur.fetchone()
    if not prospect:
        conn.close()
        return "non_trouvé"
    result = "conforme"
    if not prospect.get('source') or prospect['source'].strip() == '':
        result = "non_conforme"
    elif not prospect.get('email'):
        result = "non_conforme"
    cur.execute("""
        INSERT INTO compliance_logs (prospect_id, check_type, result, checked_at)
        VALUES (%s, %s, %s, %s)
    """, (prospect_id, 'rgpd_cndp', result, datetime.now()))
    if result == "non_conforme":
        cur.execute("UPDATE prospects SET statut = 'bloqué' WHERE id = %s", (prospect_id,))
    conn.commit()
    conn.close()
    print(f"[Compliance Agent] Prospect {prospect['nom']} : {result}")
    return result

def process_task(task_id, payload):
    prospect_id = payload.get("prospect_id")
    result = verifier_prospect(prospect_id)
    r.set(f"task:{task_id}:result", json.dumps({"status": result}))

def run():
    init_group()
    print("Compliance Agent démarré...")
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
                    except Exception as e: print(f"Erreur compliance: {e}")

if __name__ == "__main__":
    run()