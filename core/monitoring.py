import psutil
import docker
from docker.errors import DockerException
import subprocess
from .models import DockerContainer
import pynvml

try:
    docker_client = docker.from_env()
except DockerException:
    docker_client = None

def get_system_stats():
    """Get system-wide hardware statistics"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    stats = {
        'cpu': {
            'percent': cpu_percent,
            'cores': psutil.cpu_count(logical=False),
            'threads': psutil.cpu_count(logical=True)
        },
        'memory': {
            'total': memory.total,
            'available': memory.available,
            'used': memory.used,
            'percent': memory.percent
        },
        'disk': {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': disk.percent
        },
        'gpu': get_gpu_stats() if docker_client and docker_client.info().get('Runtimes', {}).get('nvidia') else None
    }
    
    return stats

def get_gpu_stats():
    try:
        result = subprocess.run([
            'nvidia-smi',
            '--query-gpu=utilization.gpu,memory.total,memory.used,memory.free,temperature.gpu,name',
            '--format=csv,noheader,nounits'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            gpu_data = result.stdout.strip().split(', ')
            memory_total = int(gpu_data[1])
            memory_used = int(gpu_data[2])
            return {
                'utilization': float(gpu_data[0]),
                'memory_total': memory_total,
                'memory_used': memory_used,
                'memory_free': int(gpu_data[3]),
                'memory_percent': (memory_used / memory_total) * 100 if memory_total > 0 else 0,
                'temperature': int(gpu_data[4]),
                'name': gpu_data[5]
            }
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass
    return None

def get_user_container_stats(container_id):
    """Get stats for a user's Docker container"""
    if not docker_client:
        return None

    try:
        container = DockerContainer.objects.get(container_id=container_id)
        docker_container = docker_client.containers.get(container_id)

        stats = docker_container.stats(stream=False)
        cpu_stats = stats['cpu_stats']
        precpu_stats = stats['precpu_stats']

        system_cpu_current = cpu_stats.get('system_cpu_usage')
        system_cpu_previous = precpu_stats.get('system_cpu_usage')

        if system_cpu_current is None or system_cpu_previous is None:
            cpu_percent = 0
        else:
            cpu_delta = cpu_stats['cpu_usage']['total_usage'] - precpu_stats['cpu_usage']['total_usage']
            system_delta = system_cpu_current - system_cpu_previous
            cpu_percent = (cpu_delta / system_delta) * 100 if system_delta > 0 else 0

        # ✅ ดึง GPU utilization จาก pynvml
        gpu_percent = 0
        try:
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            gpu_percent = util.gpu
            pynvml.nvmlShutdown()
        except Exception as e:
            print(f"[GPU] Error using pynvml: {e}")

        return {
            'cpu_percent': round(cpu_percent, 2),
            'gpu_percent': round(gpu_percent, 2),
            'memory_usage': stats['memory_stats'].get('usage', 0),
            'memory_limit': stats['memory_stats'].get('limit', 0),
            'network': stats.get('networks', {}),
            'status': container.status
        }

    except (DockerContainer.DoesNotExist, docker.errors.NotFound):
        return None