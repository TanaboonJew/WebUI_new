from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # import แล้วเรียก start_scheduler() ที่นี่
        from .scheduler import start_scheduler
        start_scheduler()
        print("[Scheduler] CoreConfig ready() called")
