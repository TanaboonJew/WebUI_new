# core/jobs.py (updated)

from .models import DockerContainer, ContainerSchedule, CustomUser
from docker import from_env
from django.utils import timezone
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.models import DjangoJobExecution
import logging
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)

def control_container(container_id, action):
    logger.info(f"[Scheduler] control_container called with container_id={container_id}, action={action}")
    
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

def restrict_access_for_privileged_user(schedule):
    """
    When a privileged user (doctoral/teacher) schedule starts:
    1. Set all other users' is_accessible to False
    2. Stop all other containers
    """
    privileged_user = schedule.container.user
    if privileged_user.role not in ['doctoral', 'teacher']:
        return
    
    logger.info(f"[Scheduler] Restricting access for privileged user {privileged_user.username}")
    
    # Set all other users to not accessible
    CustomUser.objects.exclude(id=privileged_user.id).update(is_accessible=False)
    
    # Stop all other containers
    client = from_env()
    for container in DockerContainer.objects.exclude(user=privileged_user):
        try:
            docker_container = client.containers.get(container.container_id)
            if docker_container.status == "running":
                docker_container.stop()
                logger.info(f"[Scheduler] Stopped container {container.container_id} for user {container.user.username}")
        except Exception as e:
            logger.error(f"[Scheduler][Error] Error stopping container {container.container_id}: {e}")

def restore_access_for_privileged_user(schedule):
    """
    When a privileged user (doctoral/teacher) schedule ends:
    1. Restore all users' is_accessible to True
    """
    privileged_user = schedule.container.user
    if privileged_user.role not in ['doctoral', 'teacher']:
        return
    
    logger.info(f"[Scheduler] Restoring access after privileged user {privileged_user.username}")
    
    # Restore access for all users
    CustomUser.objects.all().update(is_accessible=True)

def schedule_all_containers(scheduler):
    from .models import ContainerSchedule
    for schedule in ContainerSchedule.objects.filter(active=True):
        container = schedule.container
        container_id = container.container_id

        logger.info(f"Start datetime: {schedule.start_datetime} | End datetime: {schedule.end_datetime}")
        
        # Schedule container start/stop as before
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
        
        # Add additional jobs for privileged users
        if container.user.role in ['doctoral', 'teacher']:
            # Schedule access restriction at start time
            scheduler.add_job(
                restrict_access_for_privileged_user,
                trigger=DateTrigger(run_date=schedule.start_datetime, timezone=timezone.get_current_timezone()),
                args=[schedule],
                id=f"restrict_access_{container_id}_{schedule.start_datetime.isoformat()}",
                replace_existing=True,
            )
            
            # Schedule access restoration at end time
            scheduler.add_job(
                restore_access_for_privileged_user,
                trigger=DateTrigger(run_date=schedule.end_datetime, timezone=timezone.get_current_timezone()),
                args=[schedule],
                id=f"restore_access_{container_id}_{schedule.end_datetime.isoformat()}",
                replace_existing=True,
            )