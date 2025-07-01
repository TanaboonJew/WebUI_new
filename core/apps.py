from django.apps import AppConfig
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
import atexit

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        scheduler = BackgroundScheduler()
        scheduler.add_jobstore(DjangoJobStore(), "default")

        from .jobs import schedule_all_containers  
        schedule_all_containers(scheduler)

        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())