import os
from django.db import models
from users.models import CustomUser


def user_directory_path(instance, filename):
    """Returns: user_<ID>_(<USERNAME>)/<type>/<filename>"""
    return f'user_{instance.user.id}_({instance.user.username})/{instance._meta.model_name}s/{filename}'


def user_file_path(instance, filename):
    """Used by models that have a static file_type attribute"""
    return f"user_{instance.user.id}_({instance.user.username})/{instance.file_type}/{filename}"


class DockerContainer(models.Model):
    STATUS_CHOICES = [
        ('building', 'Building'),
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('error', 'Error')
    ]
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='containers')
    container_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='building')
    dockerfile = models.FileField(
        upload_to='dockerfiles/',
        null=False, ### change this to true when migrate
        blank=False # this too
    )
    build_logs = models.TextField(blank=True)
    jupyter_token = models.CharField(max_length=50, blank=True)
    jupyter_port = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resource_limits = models.JSONField(default=dict)
    image_name = models.CharField(max_length=255, blank=True)
    port_bindings = models.JSONField(default=dict)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Docker Container'
        verbose_name_plural = 'Docker Containers'
    
    def get_absolute_url(self):
        if self.jupyter_port:
            return f"http://localhost:{self.jupyter_port}/?token={self.jupyter_token}"
        return None

    def __str__(self):
        return f"{self.user.username}'s container ({self.status})"


class UserFile(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='user_files')
    file = models.FileField(upload_to=user_directory_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'User File'
        verbose_name_plural = 'User Files'

    def filename(self):
        return os.path.basename(self.file.name)

    def __str__(self):
        return self.filename()

    def delete(self, *args, **kwargs):
        """Delete the associated file when model is deleted"""
        self.file.delete(save=False)
        super().delete(*args, **kwargs)


class AIModel(models.Model):
    FRAMEWORKS = [
        ('tensorflow', 'TensorFlow'),
        ('pytorch', 'PyTorch'),
        ('onnx', 'ONNX'),
        ('keras', 'Keras')
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='ai_models')
    name = models.CharField(max_length=100)
    framework = models.CharField(max_length=20, choices=FRAMEWORKS)
    model_file = models.FileField(upload_to=user_file_path)
    created_at = models.DateTimeField(auto_now_add=True)
    file_type = 'models'  # Used in upload path

    class Meta:
        ordering = ['-created_at']
        unique_together = ['user', 'name']
        verbose_name = 'AI Model'
        verbose_name_plural = 'AI Models'

    def __str__(self):
        return f"{self.name} ({self.get_framework_display()})"

    def delete(self, *args, **kwargs):
        """Delete the associated model file when model is deleted"""
        self.model_file.delete(save=False)
        super().delete(*args, **kwargs)