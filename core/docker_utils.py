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
            self.client.ping()  # Test connection
        except DockerException as e:
            logger.error(f"Docker connection failed: {e}")
            self.client = None

    def _get_available_port(self) -> int:
        """Find an available port dynamically"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    def _generate_jupyter_token(self) -> str:
        """Generate secure token for Jupyter access"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=32))

    def _get_user_workspace(self, user: CustomUser) -> str:
        """Get or create user's workspace directory"""
        path = os.path.join(settings.MEDIA_ROOT, f'user_{user.id}_{user.username}')
        os.makedirs(path, exist_ok=True)
        return path

    def _prepare_user_directories(self, user: CustomUser) -> Dict[str, str]:
        """Create and return standard user directories"""
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
        """Build container from user's Dockerfile"""
        if not self.client:
            return None, "Docker not available"

        try:
            container_name = f"user_{user.id}_{user.username}"
            build_logs = []
            
            image, logs = self.client.images.build(
                path=os.path.dirname(dockerfile_path),
                dockerfile=os.path.basename(dockerfile_path),
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
        """Create and start a container for the user
        Returns tuple of (url, token) or (None, None) on failure"""
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
                
                # Save container details
                DockerContainer.objects.create(
                    user=user,
                    container_id=container.id,
                    image_name="jupyter/tensorflow-notebook",
                    status='running',
                    jupyter_token=token,
                    jupyter_port=port,
                    resource_limits={
                        'cpu': user.cpu_limit,
                        'ram': user.ram_limit,
                        'gpu': user.gpu_access
                    }
                )
                
                return f"http://localhost:{port}/?token={token}", token
                
        except Exception as e:
            logger.error(f"Container creation failed: {e}")
            return None

    def manage_container(self, user: CustomUser, action: str, container_type: str = 'default') -> bool:
        """Manage container lifecycle (start/stop/delete)"""
        if not self.client:
            return False

        try:
            container_name = f"{container_type}_{user.id}_{user.username}"
            container = self.client.containers.get(container_name)
            
            if action == 'start':
                container.start()
                status = 'running'
            elif action == 'stop':
                container.stop()
                status = 'stopped'
            elif action == 'delete':
                container.remove(force=True)
                DockerContainer.objects.filter(user=user, container_id=container.id).delete()
                return True
            else:
                raise ValueError("Invalid action")
            
            if container_type != 'jupyter':
                DockerContainer.objects.filter(
                    user=user, 
                    container_id=container.id
                ).update(status=status)
            
            return True
            
        except Exception as e:
            logger.error(f"Container {action} failed: {e}")
            return False

    def get_container_stats(self, container_id: str) -> Optional[Dict]:
        """Get container resource usage statistics"""
        if not self.client:
            return None

        try:
            container = self.client.containers.get(container_id)
            stats = container.stats(stream=False)
            
            # CPU calculation
            cpu_stats = stats['cpu_stats']
            cpu_delta = cpu_stats['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = cpu_stats['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
            cpu_percent = (cpu_delta / system_delta) * 100 if system_delta > 0 else 0

            # Memory calculation
            memory = stats['memory_stats']
            mem_usage = memory.get('usage', 0)
            mem_limit = memory.get('limit', 1)
            
            return {
                'cpu': round(cpu_percent, 2),
                'memory': mem_usage / (1024 * 1024),  # MB
                'memory_percent': (mem_usage / mem_limit) * 100,
                'network': {
                    'rx': stats['networks']['eth0']['rx_bytes'] / (1024 * 1024),
                    'tx': stats['networks']['eth0']['tx_bytes'] / (1024 * 1024)
                }
            }
        except Exception as e:
            logger.error(f"Stats collection failed: {e}")
            return None


# Global instance for convenience
docker_manager = DockerManager()

# Legacy functions for backward compatibility
def create_container(user: CustomUser, image_name: str, container_type: str = 'default') -> Optional[str]:
    return docker_manager.create_container(user, image_name, container_type)

def manage_container(user: CustomUser, action: str, container_type: str = 'default') -> bool:
    return docker_manager.manage_container(user, action, container_type)

def get_container_stats(container_id: str) -> Optional[Dict]:
    return docker_manager.get_container_stats(container_id)