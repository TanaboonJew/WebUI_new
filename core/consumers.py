import json
import psutil
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import docker
import asyncio
from .models import DockerContainer
import os
import pynvml

class MonitoringConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.keep_sending = True
        self.task = asyncio.create_task(self.send_stats_loop())

    async def disconnect(self, close_code):
        self.keep_sending = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def send_stats_loop(self):
        while self.keep_sending:
            try:
                data = await self.get_system_stats()
                await self.send(text_data=json.dumps(data))
                await asyncio.sleep(2)
            except Exception as e:
                print(f"Error sending stats: {e}")
                break

    @database_sync_to_async
    def get_system_stats(self):
        client = docker.from_env()

        gpu_data = {
            'utilization': 0,
            'memory_percent': 0,
            'temperature': 0,
        }

        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)

            gpu_data['utilization'] = util.gpu
            gpu_data['memory_percent'] = mem_info.used / mem_info.total * 100 if mem_info.total else 0
            gpu_data['temperature'] = temp

        except Exception as e:
            print(f"Error getting GPU stats: {e}")

        stats = {
            'cpu': psutil.cpu_percent(),
            'memory': psutil.virtual_memory().percent,
            'containers': len(client.containers.list()),
            'active_users': DockerContainer.objects.filter(status='running').count(),
            'gpu': gpu_data,
        }
        return stats

class ContainerConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.container_id = self.scope['url_route']['kwargs']['container_id']
        await self.accept()
        
        self.keep_sending = True
        self.task = asyncio.create_task(self.send_stats_loop())

    async def disconnect(self, close_code):
        self.keep_sending = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def send_stats_loop(self):
        while self.keep_sending:
            data = await self.get_container_stats()
            if data:
                await self.send(text_data=json.dumps(data))
            await asyncio.sleep(1)

    @database_sync_to_async
    def get_container_stats(self):
        try:
            client = docker.from_env()
            container = client.containers.get(self.container_id)
            stats = container.stats(stream=False)

            cpu_stats = stats['cpu_stats']
            precpu_stats = stats['precpu_stats']
            cpu_delta = cpu_stats['cpu_usage']['total_usage'] - precpu_stats['cpu_usage']['total_usage']
            system_delta = cpu_stats['system_cpu_usage'] - precpu_stats['system_cpu_usage']
            
            cpu_count = cpu_stats.get('online_cpus', 1)
            cpu_percent = (cpu_delta / system_delta) * cpu_count * 100 if system_delta > 0 else 0

            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            memory_percent = (memory_usage / memory_limit) * 100 if memory_limit else 0

            rx = tx = 0
            if 'networks' in stats:
                for iface in stats['networks'].values():
                    rx += iface.get('rx_bytes', 0)
                    tx += iface.get('tx_bytes', 0)

            # GPU usage
            gpu_memory_mb = 0
            try:
                pid_host = container.attrs['State']['Pid']
                pids = [pid_host]

                children_output = os.popen(f"cat /proc/{pid_host}/task/{pid_host}/children").read()
                pids += [int(pid) for pid in children_output.strip().split()] if children_output.strip() else []

                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)

                try:
                    processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
                except pynvml.NVMLError_NotSupported:
                    processes = []

                for proc in processes:
                    if proc.pid in pids:
                        used_memory = getattr(proc, 'usedGpuMemory', 0)
                        gpu_memory_mb += used_memory // (1024 * 1024)

                pynvml.nvmlShutdown()
            except Exception as e:
                print(f"[GPU] Error: {e}")
                gpu_memory_mb = 0  # fallback

            return {
                'cpu': round(cpu_percent, 2),
                'memory_usage': memory_usage,
                'memory_limit': memory_limit,
                'memory_percent': round(memory_percent, 2),
                'network_rx': round(rx / (1024 * 1024), 2),
                'network_tx': round(tx / (1024 * 1024), 2),
                'status': container.status,
                'gpu_usage': gpu_memory_mb
            }

        except Exception as e:
            print(f"Container stats error: {str(e)}")
            return None
