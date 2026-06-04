import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import requests
import redis
from dotenv import load_dotenv
from social.social_service import generer_post_complet, generer_calendrier_semaine

load_dotenv()

r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=True)
STREAM_KEY = "agent_tasks"
GROUP_NAME = "agents_group"

def init_group():
    try:
        r.xgroup_create(STREAM_KEY, GROUP_NAME, id='0', mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e): raise

def publier_sur_facebook(contenu):
    token = os.getenv('META_ACCESS_TOKEN')
    page_id = os.getenv('META_PAGE_ID')
    if not token or not page_id:
        print("[Social Agent] META_ACCESS_TOKEN manquant — post non publié")
        return None
    response = requests.post(
        f"https://graph.facebook.com/{page_id}/feed",
        data={"message": contenu, "access_token": token}
    )
    return response.json().get('id')

def process_task(task_id, payload):
    action = payload.get("action", "generer_post")
    if action == "generer_calendrier":
        posts = generer_calendrier_semaine()
        r.set(f"task:{task_id}:result", json.dumps({"status": "done", "posts": len(posts)}))
        print(f"[Social Agent] Calendrier : {len(posts)} posts générés")
    else:
        plateforme = payload.get("plateforme", "instagram")
        theme = payload.get("theme", "medina")
        langue = payload.get("langue", "français")
        post = generer_post_complet(plateforme, theme, langue)
        external_id = None
        if plateforme == "facebook":
            external_id = publier_sur_facebook(post.get('contenu', ''))
        r.set(f"task:{task_id}:result", json.dumps({
            "status": "published" if external_id else "generated",
            "post": post
        }))
        print(f"[Social Agent] Post {plateforme}/{theme} généré")

def run():
    init_group()
    print("Social Agent démarré...")
    while True:
        results = r.xreadgroup(GROUP_NAME, "social_worker", {STREAM_KEY: '>'}, count=1, block=5000)
        if not results: continue
        for stream, messages in results:
            for msg_id, data in messages:
                if data.get("agent_type") == "social":
                    r.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    task_id = data["task_id"]
                    payload = json.loads(data["payload"])
                    try: process_task(task_id, payload)
                    except Exception as e: print(f"Erreur social: {e}")

if __name__ == "__main__":
    run()