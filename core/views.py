from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from .docker_utils import docker_manager
from .file_utils import ensure_workspace_exists
from .models import DockerContainer, UserFile, AIModel
from .forms import DockerfileUploadForm, FileUploadForm, AIModelForm
from .monitoring import get_system_stats, get_user_container_stats
from django.contrib import messages
import os


def home(request):
    """Home page view that shows different content based on authentication status"""
    return render(request, 'core/home.html')


@login_required
def docker_management(request):
    user_container = DockerContainer.objects.filter(user=request.user).first()
    
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'image':
            form = DockerfileUploadForm(request.POST, request.FILES)
            if form.is_valid():
                dockerfile = form.save(commit=False)
                dockerfile.user = request.user
                dockerfile.save()
                
                image_id, logs = docker_manager.build_from_dockerfile(
                    request.user,
                    dockerfile.dockerfile.path
                )
                
                if image_id:
                    container_url = docker_manager.create_container(
                        request.user,
                        image_id=image_id,
                        container_type='custom'
                    )
                    if container_url:
                        messages.success(request, "Container built and started successfully!")
                        return redirect('docker-management')
                    else:
                        messages.error(request, "Failed to start container")
                else:
                    messages.error(request, f"Build failed: {logs}")
        else:
            messages.error(request, "Invalid form submission")
    else:
        form = DockerfileUploadForm()
    
    return render(request, 'core/docker_management.html', {
        'form': form,
        'container': user_container
    })


@login_required
def file_manager(request):
    ensure_workspace_exists(request.user)
    files = UserFile.objects.filter(user=request.user)
    
    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            new_file = form.save(commit=False)
            new_file.user = request.user
            new_file.save()
            messages.success(request, "File uploaded successfully")
            return redirect('file-manager')
    else:
        form = FileUploadForm()
    
    return render(request, 'core/file_manager.html', {
        'form': form,
        'files': files
    })


@login_required
def start_container_view(request):
    if request.method == 'POST':
        if docker_manager.manage_container(request.user, 'start'):
            messages.success(request, "Container started successfully")
        else:
            messages.error(request, "Failed to start container")
    return redirect('docker-management')


@login_required
def stop_container_view(request):
    if request.method == 'POST':
        if docker_manager.manage_container(request.user, 'stop'):
            messages.success(request, "Container stopped successfully")
        else:
            messages.error(request, "Failed to stop container")
    return redirect('docker-management')


@login_required
def delete_container_view(request):
    if request.method == 'POST':
        if docker_manager.manage_container(request.user, 'delete'):
            messages.success(request, "Container deleted successfully")
        else:
            messages.error(request, "Failed to delete container")
    return redirect('docker-management')


@login_required
def download_file(request, file_id):
    try:
        file_obj = UserFile.objects.get(id=file_id, user=request.user)
        if os.path.exists(file_obj.file.path):
            response = FileResponse(file_obj.file)
            response['Content-Disposition'] = f'attachment; filename="{file_obj.filename()}"'
            return response
        raise UserFile.DoesNotExist
    except UserFile.DoesNotExist:
        messages.error(request, "File not found")
        return redirect('file-manager')


@login_required
def delete_file(request, file_id):
    try:
        file_obj = UserFile.objects.get(id=file_id, user=request.user)
        file_path = file_obj.file.path
        if os.path.exists(file_path):
            os.remove(file_path)
        file_obj.delete()
        messages.success(request, "File deleted successfully")
    except UserFile.DoesNotExist:
        messages.error(request, "File not found")
    return redirect('file-manager')


def public_dashboard(request):
    """Public system monitoring dashboard - accessible to all users"""
    try:
        stats = get_system_stats()
        
        # Calculate free disk percentage
        if stats and 'disk' in stats:
            disk_percent = stats['disk'].get('percent', 0)
            stats['disk']['free_percent'] = 100 - disk_percent
        
        context = {
            'stats': stats,
            'websocket_url': f"ws://{request.get_host()}/ws/monitoring/",
            'show_public': True  # Always show public dashboard
        }
        return render(request, 'core/public_dashboard.html', context)
    except Exception as e:
        print(f"Monitoring error: {str(e)}")
        return render(request, 'core/public_dashboard.html', {
            'error': "Could not load monitoring data",
            'show_public': True
        })


@login_required
def private_dashboard(request):
    """Private user-specific monitoring dashboard"""
    system_stats = get_system_stats()
    container_stats = None
    
    container = DockerContainer.objects.filter(user=request.user).first()
    if container:
        container_stats = docker_manager.get_container_stats(container.container_id)
    
    return render(request, 'core/private_dashboard.html', {
        'system_stats': system_stats,
        'container_stats': container_stats,
        'user': request.user,
        'container': container
    })


@login_required
def ai_dashboard(request):
    models = AIModel.objects.filter(user=request.user)
    jupyter_token = None
    jupyter_running = False
    
    if request.method == 'POST':
        if 'start_jupyter' in request.POST:
            jupyter_url = docker_manager.create_container(
                request.user,
                container_type='jupyter'
            )
            if jupyter_url:
                messages.success(request, "Jupyter Notebook started successfully")
                # Extract token from URL
                if '?token=' in jupyter_url:
                    jupyter_token = jupyter_url.split('?token=')[1]
            else:
                messages.error(request, "Failed to start Jupyter Notebook")
        
        elif 'stop_jupyter' in request.POST:
            if docker_manager.manage_container(request.user, 'stop', container_type='jupyter'):
                messages.success(request, "Jupyter Notebook stopped successfully")
            else:
                messages.error(request, "Failed to stop Jupyter Notebook")
        
        elif 'upload_model' in request.POST:
            form = AIModelForm(request.POST, request.FILES)
            if form.is_valid():
                model = form.save(commit=False)
                model.user = request.user
                model.save()
                messages.success(request, "Model uploaded successfully")
                return redirect('ai-dashboard')
    
    # Check if Jupyter is running
    container = DockerContainer.objects.filter(
        user=request.user,
        image_name="jupyter/tensorflow-notebook"
    ).first()
    
    jupyter_running = container and container.status == 'running'
    jupyter_url = container.get_absolute_url() if container else None
    
    # Extract token if URL exists
    if jupyter_url and '?token=' in jupyter_url:
        jupyter_token = jupyter_url.split('?token=')[1]
    
    return render(request, 'core/ai_dashboard.html', {
        'models': models,
        'jupyter_url': jupyter_url,
        'jupyter_token': jupyter_token,
        'jupyter_running': jupyter_running,
        'form': AIModelForm()
    })


@login_required
def delete_model(request, model_id):
    try:
        model = AIModel.objects.get(id=model_id, user=request.user)
        model.delete()
        messages.success(request, "Model deleted successfully")
    except AIModel.DoesNotExist:
        messages.error(request, "Model not found")
    return redirect('ai-dashboard')


@login_required
def build_container(request):
    if request.method == 'POST':
        form = DockerfileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Save Dockerfile
                dockerfile = form.save(commit=False)
                dockerfile.user = request.user
                dockerfile.save()
                
                # Build container
                image_id, logs = docker_manager.build_from_dockerfile(
                    request.user, 
                    dockerfile.dockerfile.path
                )
                
                if not image_id:
                    messages.error(request, f"Build failed: {logs}")
                    return redirect('docker-management')
                
                # Run container
                container_url = docker_manager.create_container(
                    request.user,
                    image_id=image_id
                )
                
                if container_url:
                    messages.success(request, "Container built and started successfully!")
                else:
                    messages.error(request, "Container build succeeded but failed to start")
                
                return redirect('docker-management')
                
            except Exception as e:
                messages.error(request, f"Build failed: {str(e)}")
    else:
        form = DockerfileUploadForm()
    
    return render(request, 'core/build_container.html', {'form': form})

# temp for debug
from django.http import HttpResponse

def health_check(request):
    return HttpResponse("OK", status=200)