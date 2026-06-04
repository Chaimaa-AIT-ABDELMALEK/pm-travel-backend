import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import redis
from dotenv import load_dotenv
from emails.email_service import generer_contenu_email, envoyer_email

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
    prospect = {
        "nom": payload.get("name", "Client"),
        "email": payload.get("email", "test@example.com"),
        "ville": payload.get("ville", "Marrakech"),
        "secteur": payload.get("secteur", "hôtellerie"),
        "score": payload.get("score", 50)
    }
    contenu = generer_contenu_email(prospect)
    sujet = f"Offre spéciale pour {prospect['nom']}"
    success = envoyer_email(prospect['email'], sujet, contenu, prospect['nom'])
    result = {"status": "sent" if success else "failed", "to": prospect['email']}
    r.set(f"task:{task_id}:result", json.dumps(result))
    print(f"[Email Worker] {prospect['nom']} — {'envoyé' if success else 'échec'}")
    return result

def run():
    init_group()
    print("Email Worker démarré...")
    while True:
        results = r.xreadgroup(GROUP_NAME, "email_worker", {STREAM_KEY: '>'}, count=1, block=5000)
        if not results: continue
        for stream, messages in results:
            for msg_id, data in messages:
                if data.get("agent_type") == "email":
                    r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    task_id = data["task_id"]
                    payload = json.loads(data["payload"])
                    try: process_task(task_id, payload)
                    except Exception as e: print(f"Erreur: {e}")

if __name__ == "__main__":
    run()