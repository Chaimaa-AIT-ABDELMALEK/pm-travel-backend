import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
import json
from redis_client import r, STREAM_KEY, init_group
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
GROUP_NAME = "agents_group"

def generate_email(name):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Tu es un expert marketing pour une agence de voyage marocaine PM Travel basée à Marrakech."},
            {"role": "user", "content": f"Écris un email professionnel de prospection pour {name}"}
        ]
    )
    return response.choices[0].message.content

def process_task(task_id, payload):
    name = payload.get("name")
    email_content = generate_email(name)
    r.set(f"task:{task_id}:result", json.dumps({"status": "sent", "content": email_content}))
    print(f"[Email Agent] Email généré pour {name}")
    return {"status": "sent", "content": email_content}

def run():
    init_group()
    print("Email Agent démarré...")
    while True:
        results = r.xreadgroup(GROUP_NAME, "email_worker", {STREAM_KEY: '>'}, count=1, block=5000)
        if not results:
            continue
        for stream, messages in results:
            for msg_id, data in messages:
                if data.get("agent_type") == "email":
                    r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    task_id = data["task_id"]
                    payload = json.loads(data["payload"])
                    try:
                        result = process_task(task_id, payload)
                        print(f"Tâche {task_id} terminée")
                    except Exception as e:
                        print(f"Erreur tâche {task_id}: {e}")

if __name__ == "__main__":
    run()