from background_task import background
from core.docker_util import DockerManager

@background(schedule=600)  # รันครั้งแรกหลัง 10 นาที (600 วินาที)
def cleanup_containers_task():
    dm = DockerManager()
    dm.cleanup_inactive_containers(inactivity_minutes=10)
