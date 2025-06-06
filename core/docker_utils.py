import docker
from docker.errors import DockerException
import os
import logging
import random
import string
import socket
from typing import Optional, Dict, Union, Tuple
from django.conf import settings
from .models import DockerContainer
from users.models import CustomUser

logger = logging.getLogger(__name__)


class DockerManager:
    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
        except DockerException as e:
            logger.error(f"Docker connection failed: {e}")
            self.client = None

    def _get_available_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    def _generate_jupyter_token(self) -> str:
        return ''.join(random.choices(string.ascii_letters + string.digits, k=32))

    def _get_user_workspace(self, user: CustomUser) -> str:
        path = os.path.join(settings.MEDIA_ROOT, f'user_{user.id}_{user.username}')
        os.makedirs(path, exist_ok=True)
        return path

    def _prepare_user_directories(self, user: CustomUser) -> Dict[str, str]:
        user_dir = self._get_user_workspace(user)
        dirs = {
            'jupyter': os.path.join(user_dir, 'jupyter'),
            'models': os.path.join(user_dir, 'models'),
            'data': os.path.join(user_dir, 'data')
        }
        for d in dirs.values():
            os.makedirs(d, exist_ok=True)
        return dirs

    def build_from_dockerfile(self, user: CustomUser, dockerfile_path: str) -> Tuple[Optional[str], Optional[str]]:
        if not self.client:
            return None, "Docker not available"
        try:
            container_name = f"user_{user.id}_{user.username}"
            build_logs = []
            workspace_dir = self._get_user_workspace(user)
            image, logs = self.client.images.build(
                path=workspace_dir,
                dockerfile=os.path.relpath(dockerfile_path, workspace_dir),
                tag=f"{container_name}:latest",
                rm=True,
                forcerm=True,
                buildargs={
                    'USER_ID': str(user.id),
                    'USERNAME': user.username
                }
            )
            for log in logs:
                if 'stream' in log:
                    build_logs.append(log['stream'].strip())
            return image.id, "\n".join(build_logs)
        except Exception as e:
            logger.error(f"Build failed: {str(e)}")
            return None, str(e)

    def create_container(self, user: CustomUser, image_name: str, container_type: str = 'default') -> Tuple[Optional[str], Optional[str]]:
        if not self.client:
            return None, None
        try:
            dirs = self._prepare_user_directories(user)
            container_name = f"{container_type}_{user.id}_{user.username}"

            if container_type == 'jupyter':
                port = self._get_available_port()
                token = self._generate_jupyter_token()

                container = self.client.containers.run(
                    image="jupyter/tensorflow-notebook:latest",
                    name=container_name,
                    volumes={
                        dirs['jupyter']: {'bind': '/home/jovyan/work', 'mode': 'rw'},
                        dirs['models']: {'bind': '/home/jovyan/models', 'mode': 'ro'},
                        dirs['data']: {'bind': '/home/jovyan/data', 'mode': 'ro'}
                    },
                    ports={'8888/tcp': port},
                    environment={
                        'JUPYTER_TOKEN': token,
                        'GRANT_SUDO': 'yes'
                    },
                    detach=True,
                    mem_limit=f"{user.ram_limit}m",
                    cpu_shares=int(user.cpu_limit * 1024),
                    runtime='nvidia' if user.gpu_access else None
                )

                DockerContainer.objects.update_or_create(
                    user=user,
                    defaults={
                        'container_id': container.id,
                        'image_name': "jupyter/tensorflow-notebook",
                        'status': 'running',
                        'jupyter_token': token,
                        'jupyter_port': port,
                        'resource_limits': {
                            'cpu': user.cpu_limit,
                            'ram': user.ram_limit,
                            'gpu': user.gpu_access
                        }
                    }
                )

                return f"http://{settings.SERVER_IP}:{port}/?token={token}", token
            else:
                # Handle other types if needed
                pass

        except Exception as e:
            logger.error(f"Container creation failed: {e}")
            return None, None


    def manage_container(self, user: CustomUser, action: str, container_type: str = 'default') -> bool:
        if not self.client:
            return False
        container_name = f"{container_type}_{user.id}_{user.username}"
        try:
            container = self.client.containers.get(container_name)
            db_container = DockerContainer.objects.filter(user=user, container_id=container.id).first()

            if action == 'start':
                container.start()
                if db_container:
                    db_container.status = 'running'
                    db_container.save()
                logger.info(f"Started container {container_name}")

            elif action == 'stop':
                container.stop()
                if db_container:
                    db_container.status = 'stopped'
                    db_container.save()
                logger.info(f"Stopped container {container_name}")

            elif action == 'delete':
                container.remove(force=True)
                if db_container:
                    db_container.delete()
                logger.info(f"Deleted container {container_name}")

            else:
                logger.warning(f"Invalid action: {action}")
                return False

            return True

        except docker.errors.NotFound:
            logger.warning(f"Container {container_name} not found.")
            DockerContainer.objects.filter(user=user).delete()
            return False
        except Exception as e:
            logger.error(f"Container {action} failed: {e}")
            return False


    def get_container_stats(self, container_id: str) -> Optional[Dict]:
        if not self.client:
            return None
        try:
            container = self.client.containers.get(container_id)
            stats = container.stats(stream=False)

            cpu_stats = stats['cpu_stats']
            cpu_delta = cpu_stats['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = cpu_stats['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
            cpu_percent = (cpu_delta / system_delta) * 100 if system_delta > 0 else 0

            memory = stats['memory_stats']
            mem_usage = memory.get('usage', 0)
            mem_limit = memory.get('limit', 1)

            return {
                'cpu': round(cpu_percent, 2),
                'memory': mem_usage / (1024 * 1024),
                'memory_percent': (mem_usage / mem_limit) * 100,
                'network': {
                    'rx': stats['networks']['eth0']['rx_bytes'] / (1024 * 1024),
                    'tx': stats['networks']['eth0']['tx_bytes'] / (1024 * 1024)
                }
            }
        except Exception as e:
            logger.error(f"Stats collection failed: {e}")
            return None

    def start_or_resume_container(self, user: CustomUser, image_name: str, container_type: str = 'jupyter') -> Tuple[Optional[str], Optional[str]]:
        if not self.client:
            return None, None

        container_name = f"{container_type}_{user.id}_{user.username}"

        try:
            db_container = DockerContainer.objects.filter(user=user).first()

            if db_container:
                try:
                    container = self.client.containers.get(container_name)

                    if container.status != 'running':
                        container.start()
                        db_container.status = 'running'
                        db_container.save()
                        logger.info(f"Resumed container {container_name}")
                    else:
                        logger.info(f"Container {container_name} is already running")

                    port = db_container.jupyter_port
                    token = db_container.jupyter_token
                    return f"http://{settings.SERVER_IP}:{port}/?token={token}", token

                except docker.errors.NotFound:
                    logger.warning(f"Stale DB container {container_name} deleted; recreating.")
                    db_container.delete()

            return self.create_container(user, image_name, container_type)

        except Exception as e:
            logger.error(f"start_or_resume_container failed: {e}")
            return None, None


# Global instance
docker_manager = DockerManager()

# Optional aliases
def create_container(user: CustomUser, image_name: str, container_type: str = 'default') -> Optional[str]:
    return docker_manager.create_container(user, image_name, container_type)

def manage_container(user: CustomUser, action: str, container_type: str = 'default') -> bool:
    return docker_manager.manage_container(user, action, container_type)

def get_container_stats(container_id: str) -> Optional[Dict]:
    return docker_manager.get_container_stats(container_id)

def start_or_resume_container(user: CustomUser, image_name: str, container_type: str = 'jupyter') -> Tuple[Optional[str], Optional[str]]:
    return docker_manager.start_or_resume_container(user, image_name, container_type)