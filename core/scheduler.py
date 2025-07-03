import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution

scheduler = BackgroundScheduler()

def start_scheduler():
    if not scheduler.running:
        scheduler.add_jobstore(DjangoJobStore(), "default")

        from .jobs import schedule_all_containers
        schedule_all_containers(scheduler)

        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())
        print("[Scheduler] Scheduler started")

def reload_schedules():
    scheduler.remove_all_jobs()

    try:
        DjangoJobExecution.objects.all().delete()
    except Exception as e:
        print(f"[Scheduler] Warning: Failed to delete old job executions: {e}")

    from .jobs import schedule_all_containers
    schedule_all_containers(scheduler)
    print("[Scheduler] Schedules reloaded")