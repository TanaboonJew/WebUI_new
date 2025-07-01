from django.apps import AppConfig
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django.db.models.signals import post_migrate
import atexit

scheduler = BackgroundScheduler()

def start_scheduler(sender, **kwargs):
    if not scheduler.running:
        scheduler.add_jobstore(DjangoJobStore(), "default")
        from .jobs import schedule_all_containers
        schedule_all_containers(scheduler)
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())
        print("[Scheduler] Started by post_migrate signal")

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        post_migrate.connect(start_scheduler, sender=self)
        print("[Scheduler] CoreConfig ready() connected post_migrate signal")
