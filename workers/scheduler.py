import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.blocking import BlockingScheduler
from orchestrator import send_task
from dotenv import load_dotenv

load_dotenv()

scheduler = BlockingScheduler()

@scheduler.scheduled_job('interval', minutes=5)
def traiter_relances():
    send_task("email", {"action": "relances"})
    print("Relances email déclenchées")

@scheduler.scheduled_job('cron', day_of_week='mon', hour=8)
def calendrier_social():
    send_task("social", {"action": "generer_calendrier"})
    print("Calendrier social généré")

@scheduler.scheduled_job('interval', hours=1)
def analytics():
    send_task("analytics", {"action": "snapshot"})
    print("Snapshot analytics")

@scheduler.scheduled_job('cron', hour=2)
def compliance():
    send_task("compliance", {"action": "scan_all"})
    print("Scan compliance lancé")

if __name__ == "__main__":
    print("Scheduler PM Travel démarré ✅")
    scheduler.start()