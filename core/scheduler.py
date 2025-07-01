import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from .jobs import schedule_all_containers

scheduler = BackgroundScheduler()

def start_scheduler():
    if not scheduler.running:
        scheduler.add_jobstore(DjangoJobStore(), "default")
        schedule_all_containers(scheduler)
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())
        print("[Scheduler] Scheduler started")
