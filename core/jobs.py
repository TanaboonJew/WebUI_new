from .models import DockerContainer
from .models import ContainerSchedule
from docker import from_env
from django.utils import timezone
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.models import DjangoJobExecution
import logging

logger = logging.getLogger(__name__)

def control_container(container_id, action):
    client = from_env()
    try:
        container = client.containers.get(container_id)
        logger.info(f"Trying to {action} container {container_id} (status={container.status})")
        if action == "start" and container.status != "running":
            container.start()
            logger.info(f"Container {container_id} started")
        elif action == "stop" and container.status == "running":
            container.stop()
            logger.info(f"Container {container_id} stopped")
    except Exception as e:
        logger.error(f"Error {action}ing container {container_id}: {e}")


def schedule_all_containers(scheduler):
    for schedule in ContainerSchedule.objects.filter(active=True):
        container = schedule.container
        container_id = container.container_id

        # Schedule start
        scheduler.add_job(
            control_container,
            trigger=CronTrigger(hour=schedule.start_time.hour, minute=schedule.start_time.minute),
            args=[container_id, "start"],
            id=f"start_{container_id}",
            replace_existing=True,
        )

        # Schedule stop
        scheduler.add_job(
            control_container,
            trigger=CronTrigger(hour=schedule.end_time.hour, minute=schedule.end_time.minute),
            args=[container_id, "stop"],
            id=f"stop_{container_id}",
            replace_existing=True,
        )

