import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pymysql
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

def connect_db():
    return pymysql.connect(
        host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT')),
        user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'), charset='utf8mb4'
    )

def calculer_score(prospect):
    score = 0
    secteur = (prospect.get('secteur') or '').lower()
    if secteur in ['hotel', 'riad']: score += 30
    if secteur in ['agence de voyage', 'tour operator']: score += 25
    if prospect.get('email_valide'): score += 20
    if prospect.get('ville') in ['Marrakech', 'Agadir', 'Fes', 'Casablanca']: score += 15
    if prospect.get('telephone'): score += 10
    return min(score, 100)

def process_task(task_id, payload):
    prospect_id = payload.get("prospect_id")
    conn = connect_db()
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM prospects WHERE id = %s", (prospect_id,))
    prospect = cur.fetchone()
    score = 0
    if prospect:
        score = calculer_score(prospect)
        cur.execute("UPDATE prospects SET score = %s WHERE id = %s", (score, prospect['id']))
        conn.commit()
        print(f"[Prospection Agent] {prospect['nom']} scoré : {score}/100")
    conn.close()
    r.set(f"task:{task_id}:result", json.dumps({"status": "scored", "score": score}))

def run():
    init_group()
    print("Prospection Agent démarré...")
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
                    except Exception as e: print(f"Erreur prospection: {e}")

if __name__ == "__main__":
    run()