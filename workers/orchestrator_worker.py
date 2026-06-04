import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import redis
from dotenv import load_dotenv
from orchestrator import send_task

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
    workflow = payload.get("workflow", [])
    results = []
    for step in workflow:
        agent_type = step.get("agent")
        step_payload = step.get("payload", {})
        new_task_id = send_task(agent_type, step_payload)
        results.append({"step": agent_type, "task_id": new_task_id})
        print(f"[Orchestrator] Tâche {agent_type} envoyée : {new_task_id}")
    result = {"workflow_results": results}
    r.set(f"task:{task_id}:result", json.dumps(result))
    return result

def run():
    init_group()
    print("Orchestrator Worker démarré...")
    while True:
        results = r.xreadgroup(GROUP_NAME, "orchestrator_worker", {STREAM_KEY: '>'}, count=1, block=5000)
        if not results: continue
        for stream, messages in results:
            for msg_id, data in messages:
                if data.get("agent_type") == "orchestrator":
                    r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    task_id = data["task_id"]
                    payload = json.loads(data["payload"])
                    try: process_task(task_id, payload)
                    except Exception as e: print(f"Erreur orchestrator: {e}")

if __name__ == "__main__":
    run()