from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    # Resource allocation fields
    ram_limit = models.PositiveIntegerField(default=15360)  # 15GB in MB
    storage_limit = models.PositiveIntegerField(default=51200)  # 50GB in MB
    cpu_limit = models.PositiveIntegerField(default=4)  # 4 cores
    gpu_access = models.BooleanField(default=False)
    active_container = models.OneToOneField(
        'core.DockerContainer', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='active_user'
    )
    
    def storage_used(self):
        # Calculate actual storage used
        return sum(f.file.size for f in self.user_files.all())