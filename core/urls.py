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
    path('super/', views.superuser_dashboard, name='superuser-dashboard'),
    path('api/usage-data/', views.api_usage_data, name='api_usage_data'),
    path('approve-users/', views.approve_users, name='approve_users'),
    path('request-role/', views.request_role_verification, name='request_role_verification'),
    path('allocate/<int:user_id>/', views.allocate_resources, name='allocate-resources'),
    path('containers/freeze/<int:user_id>/', views.freeze_container, name='freeze-container'),
    path('containers/resume/<int:user_id>/', views.resume_container, name='resume-container'),

]