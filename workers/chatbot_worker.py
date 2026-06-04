import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import redis
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=True)
STREAM_KEY = "agent_tasks"
GROUP_NAME = "agents_group"

def init_group():
    try:
        r.xgroup_create(STREAM_KEY, GROUP_NAME, id='0', mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e): raise

def process_task(task_id, payload):
    user_msg = payload.get("message", "Bonjour")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """Tu es l'assistant virtuel de PM Travel Agency, agence de voyage basée à Marrakech.
Tu réponds en français, anglais ou espagnol selon la langue du client.
Tu proposes : circuits désert Sahara, riads Marrakech, excursions Atlas, séjours luxe.
Si le client veut réserver, dis-lui qu'un conseiller va le contacter sous 24h."""
            },
            {"role": "user", "content": user_msg}
        ]
    )
    reply = response.choices[0].message.content
    r.set(f"task:{task_id}:result", json.dumps({"reply": reply}))
    print(f"[Chatbot Worker] Réponse générée")
    return {"reply": reply}

def run():
    init_group()
    print("Chatbot Worker démarré...")
    while True:
        results = r.xreadgroup(GROUP_NAME, "chatbot_worker", {STREAM_KEY: '>'}, count=1, block=5000)
        if not results: continue
        for stream, messages in results:
            for msg_id, data in messages:
                if data.get("agent_type") == "chatbot":
                    r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    task_id = data["task_id"]
                    payload = json.loads(data["payload"])
                    try: process_task(task_id, payload)
                    except Exception as e: print(f"Erreur: {e}")

if __name__ == "__main__":
    run()