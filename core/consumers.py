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
        while True:
            data = await self.get_system_stats()
            await self.send(text_data=json.dumps(data))
            await asyncio.sleep(2)

    @database_sync_to_async
    def get_system_stats(self):
        client = docker.from_env()
        stats = {
            'cpu': psutil.cpu_percent(),
            'memory': psutil.virtual_memory().percent,
            'containers': len(client.containers.list()),
            'active_users': DockerContainer.objects.filter(status='running').count()
        }
        return stats

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