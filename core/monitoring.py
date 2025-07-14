import psutil
import docker
from docker.errors import DockerException
import subprocess
from .models import DockerContainer
import os
import pynvml  # ✅ เพิ่มการ import

try:
    docker_client = docker.from_env()
except DockerException:
    docker_client = None


def get_system_stats():
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        try:
            gpu_stats = get_gpu_stats() if docker_client and docker_client.info().get('Runtimes', {}).get('nvidia') else None
        except Exception as e:
            print(f"GPU stats error: {e}")
            gpu_stats = None

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
            'gpu': gpu_stats
        }

        return stats

    except Exception as e:
        print(f"System stats error: {e}")
        return {}

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
    if not docker_client:
        return None

    try:
        container = DockerContainer.objects.get(container_id=container_id)
        user = getattr(container, 'active_user', None)
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

        if user and user.cpu_limit > 0:
            cpu_percent = cpu_percent / user.cpu_limit

        # 🎯 GPU Memory usage
        gpu_memory_mb = 0
        try:
            inspect = docker_container.attrs
            pid_host = inspect["State"]["Pid"]
            pids = get_all_child_pids(pid_host) if pid_host else []

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)

            processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
            for proc in processes:
                if proc.pid in pids:
                    used_memory = getattr(proc, 'usedGpuMemory', 0)
                    gpu_memory_mb += used_memory // (1024 * 1024)

            pynvml.nvmlShutdown()

        except Exception as e:
            print(f"[GPU] Error using pynvml: {e}")
            gpu_memory_mb = 0

        return {
            'cpu_percent': round(cpu_percent, 2),
            'gpu_memory_mb': gpu_memory_mb,
            'memory_usage': stats['memory_stats'].get('usage', 0),
            'memory_limit': stats['memory_stats'].get('limit', 0),
            'network': stats.get('networks', {}),
            'status': container.status
        }

    except (DockerContainer.DoesNotExist, docker.errors.NotFound):
        return None
