from .models import DockerContainer, ContainerSchedule, CustomUser
from docker import from_env
from django.utils import timezone
from apscheduler.triggers.date import DateTrigger
import logging

logger = logging.getLogger(__name__)

def stop_all_except(scheduler_user):
    logger.info(f"[Scheduler] stop_all_except: only {scheduler_user.username} remains active")
    client = from_env()
    
    # Set all users as inaccessible except the scheduled one
    CustomUser.objects.exclude(id=scheduler_user.id).update(is_accessible=False)
    scheduler_user.is_accessible = True
    scheduler_user.save()

    # Stop all containers except the scheduled one
    for container in DockerContainer.objects.exclude(user=scheduler_user):
        try:
            docker_container = client.containers.get(container.container_id)
            if docker_container.status == 'running':
                docker_container.pause()
                logger.info(f"[Scheduler] Paused container {container.container_id} for user {container.user.username}")
            container.status = 'paused'
            container.save()
        except Exception as e:
            logger.error(f"[Scheduler][Error] Failed to stop container {container.container_id}: {e}")

def reset_access_and_restart():
    logger.info("[Scheduler] reset_access_and_restart: granting access to all users")
    client = from_env()

    # Set all users accessible
    CustomUser.objects.update(is_accessible=True)

    # Optionally restart containers that were previously running
    for container in DockerContainer.objects.all():
        try:
            docker_container = client.containers.get(container.container_id)
            if container.status == 'paused':
                docker_container.unpause()
                logger.info(f"[Scheduler] Unpaused container {container.container_id} for user {container.user.username}")
                container.status = 'running'
                container.save()
        except Exception as e:
            logger.error(f"[Scheduler][Error] Failed to restart container {container.container_id}: {e}")

def schedule_all_containers(scheduler):
    schedules = ContainerSchedule.objects.filter(active=True)
    logger.info(f"[Scheduler] Found {schedules.count()} active schedules")

    from django.utils.timezone import now

    for schedule in schedules:
        container = schedule.container
        user = container.user

        if user.role not in ['doctoral', 'teacher']:
            logger.warning(f"[Scheduler] Skipping schedule for user {user.username} with role {user.role}")
            continue

        if schedule.start_datetime < now():
            logger.warning(f"[Scheduler] Skipping past schedule for user {user.username} starting at {schedule.start_datetime}")
            continue

        container_id = container.container_id
        logger.info(f"Scheduling for user {user.username} from {schedule.start_datetime} to {schedule.end_datetime}")

        scheduler.add_job(
            stop_all_except,
            trigger=DateTrigger(run_date=schedule.start_datetime, timezone=timezone.get_current_timezone()),
            args=[user],
            id=f"exclusive_start_{container_id}_{schedule.start_datetime.isoformat()}",
            replace_existing=True
        )

        scheduler.add_job(
            reset_access_and_restart,
            trigger=DateTrigger(run_date=schedule.end_datetime, timezone=timezone.get_current_timezone()),
            id=f"exclusive_end_{container_id}_{schedule.end_datetime.isoformat()}",
            replace_existing=True
        )
