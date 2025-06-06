# Generated by Django 5.2.1 on 2025-05-25 20:05

import core.models
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AIModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('framework', models.CharField(choices=[('tensorflow', 'TensorFlow'), ('pytorch', 'PyTorch'), ('onnx', 'ONNX'), ('keras', 'Keras')], max_length=20)),
                ('model_file', models.FileField(upload_to=core.models.user_file_path)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'AI Model',
                'verbose_name_plural': 'AI Models',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DockerContainer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('container_id', models.CharField(blank=True, max_length=64)),
                ('status', models.CharField(choices=[('building', 'Building'), ('running', 'Running'), ('stopped', 'Stopped'), ('error', 'Error')], default='building', max_length=20)),
                ('dockerfile', models.FileField(upload_to='dockerfiles/')),
                ('build_logs', models.TextField(blank=True)),
                ('jupyter_token', models.CharField(blank=True, max_length=50)),
                ('jupyter_port', models.PositiveIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('resource_limits', models.JSONField(default=dict)),
                ('image_name', models.CharField(blank=True, max_length=255)),
                ('port_bindings', models.JSONField(default=dict)),
            ],
            options={
                'verbose_name': 'Docker Container',
                'verbose_name_plural': 'Docker Containers',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='UserFile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to=core.models.user_directory_path)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'User File',
                'verbose_name_plural': 'User Files',
                'ordering': ['-uploaded_at'],
            },
        ),
    ]
