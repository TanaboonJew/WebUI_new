import json
import psutil
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import docker
import asyncio
from .models import DockerContainer

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
        usages = []
        # สมมติ query DockerContainer หรือ model ที่เก็บ usage ของแต่ละ user
        containers = DockerContainer.objects.all()
        for c in containers:
            usages.append({
                'username': c.user.username,
                'docker_status': c.status,
                'jupyter_status': c.jupyter_status if hasattr(c, 'jupyter_status') else 'stopped',
                'disk_usage': c.disk_usage if hasattr(c, 'disk_usage') else 'N/A',
                'cpu_usage': c.cpu_usage if hasattr(c, 'cpu_usage') else 0,
                'gpu_usage': c.gpu_usage if hasattr(c, 'gpu_usage') else 0,
                'updated_at': c.updated_at.strftime('%Y-%m-%d %H:%M:%S') if c.updated_at else ''
            })
        return {'usages': usages}

class ContainerConsumer(AsyncWebsocketConsumer):  # Add this class
    async def connect(self):
        self.container_id = self.scope['url_route']['kwargs']['container_id']
        await self.accept()
        
        while True:
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
            cpu_delta = cpu_stats['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = cpu_stats['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
            cpu_percent = (cpu_delta / system_delta) * 100 if system_delta > 0 else 0
            
            return {
                'cpu': round(cpu_percent, 2),
                'memory': stats['memory_stats']['usage'] / (1024 * 1024),  # MB
                'network': stats['networks']['eth0']['rx_bytes'] / (1024 * 1024)  # MB
            }
        except Exception as e:
            print(f"Container stats error: {str(e)}")
            return None