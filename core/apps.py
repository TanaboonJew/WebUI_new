from django.db.utils import OperationalError
from django.apps import apps

def ready(self):
    try:
        # เช็คว่าตาราง ContainerSchedule มีอยู่หรือไม่
        if apps.get_model('core', 'ContainerSchedule').objects.exists():
            from .scheduler import start_scheduler
            start_scheduler()
    except OperationalError:
        # migration ยังไม่เสร็จดี
        pass
