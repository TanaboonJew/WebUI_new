from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import atexit
        from apscheduler.schedulers.background import BackgroundScheduler
        from django_apscheduler.jobstores import DjangoJobStore
        from .jobs import schedule_all_containers

        print("[Scheduler] CoreConfig ready() called")  # ✅ ใส่ print ตรวจสอบ
        scheduler = BackgroundScheduler()
        scheduler.add_jobstore(DjangoJobStore(), "default")

        schedule_all_containers(scheduler)

        scheduler.start()
        atexit.register(lambda: scheduler.shutdown())

