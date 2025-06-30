import psutil
import docker
from docker.errors import DockerException
import subprocess
from .models import DockerContainer
import os

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

def get_all_child_pids(pid):
    pids = [pid]
    try:
        children = os.popen(f"cat /proc/{pid}/task/{pid}/children").read().strip()
        if children:
            for child_pid in children.split():
                pids.extend(get_all_child_pids(int(child_pid)))
    except Exception as e:
        print(f"[PID] Error reading children: {e}")
    return pids

def get_user_container_stats(container_id):
    """Get stats for a user's Docker container"""
    if not docker_client:
        return None

    try:
        # Get the container model instance
        container = DockerContainer.objects.get(container_id=container_id)
        # Get user who owns this container
        user = getattr(container, 'active_user', None)

        docker_container = docker_client.containers.get(container_id)

        # Get container stats from Docker API
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

        # Normalize CPU percent by user cpu_limit if available
        if user and user.cpu_limit > 0:
            cpu_percent = cpu_percent / user.cpu_limit

        # Calculate GPU memory usage per container (MB)
        gpu_memory_mb = 0
        try:
            inspect = docker_container.attrs
            pid_host = inspect["State"]["Pid"]
            if pid_host != 0:
                pids = get_all_child_pids(pid_host)
            else:
                pids = []

            import pynvml
            pynvml.nvmlInit()

            gpu_utilization = 0
            handle = None

            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception as e:
                print(f"[GPU] Error getting handle: {e}")

            if handle:
                try:
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    gpu_utilization = util.gpu  # %
                except pynvml.NVMLError as e:
                    print(f"[GPU] Utilization error: {e}")

                try:
                    processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
                except pynvml.NVMLError_NotSupported:
                    processes = []
            else:
                processes = []

            gpu_memory_mb = 0
            for proc in processes:
                if proc.pid in pids:
                    used_memory = getattr(proc, 'usedGpuMemory', 0)
                    gpu_memory_mb += used_memory // (1024 * 1024)

            pynvml.nvmlShutdown()

        except Exception as e:
            print(f"[GPU] Error using pynvml: {e}")
            gpu_utilization = 0
            gpu_memory_mb = 0

        print(f"[DEBUG] GPU percent: {gpu_utilization}, GPU memory MB: {gpu_memory_mb}")
        return {
            'cpu_percent': round(cpu_percent, 2),
            'gpu_percent': gpu_utilization,
            'gpu_memory_mb': gpu_memory_mb,
            'memory_usage': stats['memory_stats'].get('usage', 0),
            'memory_limit': stats['memory_stats'].get('limit', 0),
            'network': stats.get('networks', {}),
            'status': container.status
        }

    except (DockerContainer.DoesNotExist, docker.errors.NotFound):
        return None
