import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pymysql
import redis
from openai import OpenAI
from datetime import datetime
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

def connect_db():
    return pymysql.connect(
        host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT')),
        user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'), charset='utf8mb4'
    )

def generer_reponse(message_client):
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
            {"role": "user", "content": message_client}
        ]
    )
    return response.choices[0].message.content

def process_task(task_id, payload):
    message = payload.get("message", "")
    platform = payload.get("platform", "whatsapp")
    session_id = payload.get("session_id", task_id)
    reponse = generer_reponse(message)
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO chatbot_conversations (session_id, platform, messages, created_at)
        VALUES (%s, %s, %s, %s)
    """, (session_id, platform, json.dumps([
        {"role": "user", "content": message},
        {"role": "assistant", "content": reponse}
    ]), datetime.now()))
    conn.commit()
    conn.close()
    r.set(f"task:{task_id}:result", json.dumps({"status": "replied", "response": reponse}))
    print(f"[Chatbot Agent] Réponse générée pour session {session_id}")

def run():
    init_group()
    print("Chatbot Agent démarré...")
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
                    except Exception as e: print(f"Erreur chatbot: {e}")

if __name__ == "__main__":
    run()