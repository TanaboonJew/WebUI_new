from .models import DockerContainer
from docker import from_env
from django.utils import timezone
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.models import DjangoJobExecution
import logging
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)

def control_container(container_id, action):
    client = from_env()
    try:
        container = client.containers.get(container_id)
        logger.info(f"[Scheduler] Trying to {action} container {container_id}, current status: {container.status}")
        
        if action == "start" and container.status != "running":
            container.start()
            logger.info(f"[Scheduler] Container {container_id} started")
        elif action == "stop" and container.status == "running":
            container.stop()
            logger.info(f"[Scheduler] Container {container_id} stopped")
        else:
            logger.info(f"[Scheduler] No action taken for container {container_id} with action {action}")
    except Exception as e:
        logger.error(f"[Scheduler][Error] Error {action}ing container {container_id}: {e}")



def schedule_all_containers(scheduler):
    from .models import ContainerSchedule
    for schedule in ContainerSchedule.objects.filter(active=True):
        container = schedule.container
        container_id = container.container_id

        logger.info(f"Scheduling start job for container {container_id} at {schedule.start_datetime}")
        scheduler.add_job(
            control_container,
            trigger=DateTrigger(run_date=schedule.start_datetime, timezone=timezone.get_current_timezone()),
            args=[container_id, "start"],
            id=f"start_{container_id}_{schedule.start_datetime.isoformat()}",
            replace_existing=True,
        )

        logger.info(f"Scheduling stop job for container {container_id} at {schedule.end_datetime}")
        scheduler.add_job(
            control_container,
            trigger=DateTrigger(run_date=schedule.end_datetime, timezone=timezone.get_current_timezone()),
            args=[container_id, "stop"],
            id=f"stop_{container_id}_{schedule.end_datetime.isoformat()}",
            replace_existing=True,
        )
