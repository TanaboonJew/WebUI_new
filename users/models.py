from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('bachelor', "ปริญญาตรี"),
        ('master', "ปริญญาโท"),
        ('doctoral', "ปริญญาเอก"),
        ('teacher', "อาจารย์"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='bachelor')
    intended_role = models.CharField(max_length=20, choices=ROLE_CHOICES, null=True, blank=True)
    role_verified = models.BooleanField(default=False)

    ram_limit = models.PositiveIntegerField(default=15360)
    storage_limit = models.PositiveIntegerField(default=51200)
    cpu_limit = models.PositiveIntegerField(default=4)
    gpu_access = models.BooleanField(default=False)
    active_container = models.OneToOneField(
        'core.DockerContainer',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='active_user'
    )

    def storage_used(self):
        return sum(f.file.size for f in self.user_files.all())