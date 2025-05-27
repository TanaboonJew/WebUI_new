from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('docker/', views.docker_management, name='docker-management'),
    path('files/', views.file_manager, name='file-manager'),
    path('docker/start/', views.start_container_view, name='start-container'),
    path('docker/stop/', views.stop_container_view, name='stop-container'),
    path('docker/delete/', views.delete_container_view, name='delete-container'),
    path('files/download/<int:file_id>/', views.download_file, name='download-file'),
    path('files/delete/<int:file_id>/', views.delete_file, name='delete-file'),
    path('monitoring/', views.public_dashboard, name='public-monitoring'),
    path('monitoring/private/', views.private_dashboard, name='private-monitoring'),
    path('ai/', views.ai_dashboard, name='ai-dashboard'),
    path('ai/delete/<int:model_id>/', views.delete_model, name='delete-model'),
    path('file-action/', views.file_action, name='file-action'),

]