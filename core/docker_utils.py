import docker
from docker.errors import DockerException
import os
import random
import shutil
import socket
import string
from typing import Dict, Optional, Tuple
from django.conf import settings
from .models import DockerContainer, CustomUser
import logging
import subprocess

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

    def _copy_user_uploaded_files(self, user: CustomUser, dirs: Dict[str, str]):
        base_user_path = os.path.join(settings.MEDIA_ROOT, f'user_{user.id}_{user.username}')
        src_data_dir = os.path.join(base_user_path, 'user_data')
        src_model_dir = os.path.join(base_user_path, 'user_model')

        # Copy user_data -> data/
        if os.path.exists(src_data_dir):
            for root, _, files in os.walk(src_data_dir):
                for file in files:
                    src_file = os.path.join(root, file)
                    rel_path = os.path.relpath(src_file, src_data_dir)
                    dst_file = os.path.join(dirs['data'], rel_path)
                    os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                    shutil.copy2(src_file, dst_file)

        # Copy user_model -> models/
        if os.path.exists(src_model_dir):
            for root, _, files in os.walk(src_model_dir):
                for file in files:
                    src_file = os.path.join(root, file)
                    rel_path = os.path.relpath(src_file, src_model_dir)
                    dst_file = os.path.join(dirs['models'], rel_path)
                    os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                    shutil.copy2(src_file, dst_file)

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

    def _clear_user_mount_dirs(self, dirs: Dict[str, str]):
        for path in [dirs['data'], dirs['models'], dirs['work']]:
            if os.path.exists(path):
                shutil.rmtree(path)
                os.makedirs(path, exist_ok=True)

    def create_container(self, user: CustomUser, image_name: str, container_type: str = 'default') -> Tuple[Optional[str], Optional[str]]:
        if not self.client:
            return None, None
        try:
            dirs = self._prepare_user_directories(user)
            self._clear_user_mount_dirs(dirs)
            self._copy_user_uploaded_files(user, dirs)

            container_name = f"{container_type}_{user.id}_{user.username}"

            if container_type == 'jupyter':
                port = self._get_available_port()
                token = self._generate_jupyter_token()

                container = self.client.containers.run(
                    image=f"{image_name}:latest",
                    name=container_name,
                    volumes={
                        dirs['work']: {'bind': '/home/user/work', 'mode': 'rw'},
                        dirs['models']: {'bind': '/home/user/models', 'mode': 'rw'},
                        dirs['data']: {'bind': '/home/user/data', 'mode': 'rw'}
                    },
                    ports={'8888/tcp': port},
                    environment={
                        'JUPYTER_TOKEN': token,
                        'GRANT_SUDO': 'yes'
                    },
                    detach=True,
                    mem_limit=f"{user.mem_limit}m",                  # e.g. 8192 MB
                    memswap_limit=f"{user.memswap_limit}m",          # e.g. 12288 MB
                    nano_cpus=int(user.cpu_limit * 1e9),                             # e.g. 3.0 (strict)
                    runtime='nvidia' if user.gpu_access else None
                )


                DockerContainer.objects.update_or_create(
                    user=user,
                    defaults={
                        'container_id': container.id,
                        'image_name': f"{image_name}:latest",
                        'status': 'running',
                        'jupyter_token': token,
                        'jupyter_port': port,
                        'resource_limits': {
                            'cpu': user.cpu_limit,
                            'ram': user.mem_limit,
                            'gpu': user.gpu_access
                        }
                    }
                )

                return f"http://{settings.SERVER_IP}:{port}/?token={token}", token

            else:
                pass  # สำหรับ container ประเภทอื่น

        except Exception as e:
            logger.error(f"Container creation failed: {e}")
            return None, None

    def manage_container(self, user: CustomUser, action: str, container_type: str = 'default', by_admin: bool = False) -> bool:
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
                    db_container.can_user_start = True
                    db_container.save()
                logger.info(f"Started container {container_name}")

            elif action == 'stop':
                container.stop()
                if db_container:
                    db_container.status = 'stopped'
                    db_container.can_user_start = not by_admin
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
            DockerContainer.objects.filter(user=user).delete()
            return False
        except Exception as e:
            logger.error(f"[{action.upper()}] Container error for {user.username}: {e}")
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

            # === GPU Usage via nvidia-smi ===
            container_pids = set()
            top_result = container.top()
            for proc in top_result.get('Processes', []):
                container_pids.add(proc[1])  # PID column

            result = subprocess.run(
                ['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'],
                stdout=subprocess.PIPE, text=True
            )
            gpu_mem_mb = 0
            for line in result.stdout.strip().split('\n'):
                pid, mem = line.strip().split(',')
                if pid.strip() in container_pids:
                    gpu_mem_mb += int(mem.strip())

            return {
                'cpu': round(cpu_percent, 2),
                'memory': mem_usage / (1024 * 1024),
                'memory_percent': (mem_usage / mem_limit) * 100,
                'gpu_memory_mb': gpu_mem_mb,
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
