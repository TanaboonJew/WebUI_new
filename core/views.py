from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import FileResponse, Http404, HttpResponseForbidden
from .docker_utils import docker_manager, manage_container
from .file_utils import ensure_workspace_exists
from .models import DockerContainer, UserFile, AIModel, CustomUser
from .forms import DockerfileUploadForm, FileUploadForm, AIModelForm, DockerImageForm
from .monitoring import get_system_stats, get_user_container_stats
from django.contrib import messages
from django.conf import settings
from collections import defaultdict
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.utils import timezone
import os

def home(request):
    """Home page view that shows different content based on authentication status"""
    return render(request, 'core/home.html')


@login_required
def docker_management(request):
    user_container = DockerContainer.objects.filter(user=request.user).first()
    dockerfile_form = DockerfileUploadForm()
    image_form = DockerImageForm()

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'dockerfile':
            dockerfile_form = DockerfileUploadForm(request.POST, request.FILES)
            if dockerfile_form.is_valid():
                dockerfile = dockerfile_form.cleaned_data['dockerfile']
                
                # สร้างหรืออัพเดต DockerContainer object
                container, created = DockerContainer.objects.get_or_create(user=request.user)
                container.dockerfile.save(dockerfile.name, dockerfile)
                container.status = 'building'
                container.save()

                # build image จาก dockerfile.path
                dockerfile_path = container.dockerfile.path
                image_id, logs = docker_manager.build_from_dockerfile(
                    request.user,
                    dockerfile_path
                )
                
                container.build_logs = logs
                if image_id:
                    container.image_name = image_id
                    container.status = 'running'
                    container.save()
                    container_url = docker_manager.create_container(
                        request.user,
                        image_name=image_id,
                        container_type='custom'
                    )
                    if container_url:
                        messages.success(request, "Container built and started successfully!")
                        return redirect('docker-management')
                    else:
                        container.status = 'error'
                        container.save()
                        messages.error(request, "Failed to start container")
                else:
                    container.status = 'error'
                    container.save()
                    messages.error(request, f"Build failed: {logs}")

        elif form_type == 'image':
            image_form = DockerImageForm(request.POST)
            if image_form.is_valid():
                image_name = image_form.cleaned_data['image_name']
                container_url = docker_manager.create_container(
                    request.user,
                    image_name=image_name,
                    container_type='image'
                )
                if container_url:
                    messages.success(request, "Container created from image successfully!")
                    return redirect('docker-management')
                else:
                    messages.error(request, "Failed to create container from image")

        else:
            messages.error(request, "Invalid form submission")

    return render(request, 'core/docker_management.html', {
        'container': user_container,
        'dockerfile_form': dockerfile_form,
        'image_form': image_form
    })

    

@login_required
def file_manager(request):
    files = UserFile.objects.filter(user=request.user)

    if request.method == 'POST':
        uploaded_files = request.FILES.getlist('files')

        for uploaded_file in uploaded_files:
            user_file = UserFile(user=request.user)
            user_file.file.save(uploaded_file.name, uploaded_file)
            user_file.save()

        messages.success(request, "Files uploaded successfully")
        return redirect('file-manager')

    return render(request, 'core/file_manager.html', {
        'files': files,
    })


@login_required
def start_container_view(request):
    user = request.user
    success = docker_manager.manage_container(user, action='start', container_type='jupyter')
    if success:
        messages.success(request, "Container started successfully.")
    else:
        messages.error(request, "Failed to start container.")
    return redirect('docker-management')


@login_required
def stop_container_view(request):
    user = request.user
    success = manage_container(user, action='stop', container_type='jupyter') 
    if success:
        messages.success(request, "Container stopped successfully.")
    else:
        messages.warning(request, "Could not stop container.")
    return redirect('docker-management')

@login_required
def delete_container_view(request):
    if request.method == 'POST':
        success = docker_manager.manage_container(request.user, action='delete', container_type='jupyter')
        if success:
            messages.success(request, "Container deleted successfully.")
        else:
            messages.error(request, "Failed to delete container.")
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
    jupyter_url = None
    form = AIModelForm()

    if request.method == 'POST':
        if 'start_jupyter' in request.POST:
            model_id = request.POST.get('model_id')
            if not model_id:
                messages.error(request, "No model selected.")
                return redirect('ai-dashboard')

            try:
                model = AIModel.objects.get(id=model_id, user=request.user)
                framework = model.framework.lower().strip()

                image_map = {
                    'tensorflow': 'my-tf:2.19',
                    'keras': 'jupyter/tensorflow-notebook',
                    'pytorch': 'my-torch:2.6',    
                    'onnx': 'jupyter/scipy-notebook'             
                }

                print(f"Selected Model: {model.name}")
                print(f"Framework: {framework}")

                if framework not in image_map:
                    messages.error(request, f"Unsupported framework: {framework}")
                    return redirect('ai-dashboard')

                image_name = image_map[framework]

                container_result = docker_manager.start_or_resume_container(
                    request.user,
                    image_name=image_name,
                    container_type='jupyter'
                )

                if container_result:
                    if isinstance(container_result, tuple) and len(container_result) == 2:
                        jupyter_url, jupyter_token = container_result
                    else:
                        jupyter_url = container_result
                        jupyter_token = None

                    messages.success(request, f"Jupyter Notebook started! Token: {jupyter_token or 'N/A'}")
                else:
                    messages.error(request, "Failed to start Jupyter Notebook")

            except AIModel.DoesNotExist:
                messages.error(request, "Model not found.")
                return redirect('ai-dashboard')

        elif 'stop_jupyter' in request.POST:
            if docker_manager.manage_container(request.user, 'stop', container_type='jupyter'):
                messages.success(request, "Jupyter Notebook stopped successfully")
            else:
                messages.error(request, "Failed to stop Jupyter Notebook")

        elif 'upload_model' in request.POST:
            form = AIModelForm(request.POST, request.FILES)
            if form.is_valid():
                model_file = form.cleaned_data['model_file']
                name = form.cleaned_data['name'].strip()
                framework = form.cleaned_data['framework'].strip().lower()

                if not name:
                    name = os.path.splitext(model_file.name)[0]

                if AIModel.objects.filter(user=request.user, name=name).exists():
                    form.add_error('name', 'You already have a model with this name.')
                else:
                    model = AIModel(
                        user=request.user,
                        name=name,
                        framework=framework,
                    )
                    model.model_file.save(model_file.name, model_file)
                    model.save()

                    messages.success(request, "Model uploaded successfully")
                    return redirect('ai-dashboard')

    
    return render(request, 'core/ai_dashboard.html', {
        'models': models,
        'form': form,
        'jupyter_token': jupyter_token,
        'jupyter_url': jupyter_url,
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

from django.http import JsonResponse
import shutil

def get_clipboard(request):
    return request.session.get('clipboard', {})

def set_clipboard(request, action, src_path):
    request.session['clipboard'] = {'action': action, 'src': src_path}

def clear_clipboard(request):
    if 'clipboard' in request.session:
        del request.session['clipboard']


@login_required
def file_action(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        file_id = request.POST.get('file_id')

        try:
            file_obj = UserFile.objects.get(id=file_id, user=request.user)
            file_path = file_obj.file.path

            if action in ['cut', 'copy']:
                set_clipboard(request, action, file_path)
                return JsonResponse({'success': True})

            elif action == 'paste':
                clipboard = get_clipboard(request)
                if not clipboard:
                    return JsonResponse({'success': False, 'error': 'Clipboard empty'})
                
                dest_dir = os.path.dirname(file_path)
                filename = os.path.basename(clipboard['src'])
                dest_path = os.path.join(dest_dir, filename)

                if clipboard['action'] == 'copy':
                    if os.path.isdir(clipboard['src']):
                        shutil.copytree(clipboard['src'], dest_path)
                    else:
                        shutil.copy2(clipboard['src'], dest_path)

                elif clipboard['action'] == 'cut':
                    shutil.move(clipboard['src'], dest_path)
                    clear_clipboard(request)

                return JsonResponse({'success': True})

            elif action == 'rename':
                new_name = request.POST.get('new_name')
                new_path = os.path.join(os.path.dirname(file_path), new_name)
                os.rename(file_path, new_path)
                file_obj.file.name = os.path.relpath(new_path, settings.MEDIA_ROOT)
                file_obj.save()
                return JsonResponse({'success': True})

            elif action == 'move':
                new_path = request.POST.get('new_path')
                shutil.move(file_path, new_path)
                file_obj.file.name = os.path.relpath(new_path, settings.MEDIA_ROOT)
                file_obj.save()
                return JsonResponse({'success': True})

        except UserFile.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'File not found'})

    return JsonResponse({'success': False, 'error': 'Invalid request'})


# temp for debug
from django.http import HttpResponse

def health_check(request):
    return HttpResponse("OK", status=200)

@login_required
def superuser_dashboard(request):
    if not request.user.is_superuser:
        return redirect('home')

    User = get_user_model()
    users = User.objects.all()
    usages = []

    for user in users:
        if not isinstance(user, CustomUser):  # ป้องกัน type error
            continue

        container = DockerContainer.objects.filter(user=user).first()

        if container:
            stats = get_user_container_stats(container.container_id)
            docker_status = container.status
            jupyter_status = 'running' if container.status == 'running' else 'stopped'
            cpu_usage = stats.get('cpu_percent', 0)
            gpu_usage = stats.get('gpu_percent', 0)
        else:
            docker_status = 'stopped'
            jupyter_status = 'stopped'
            cpu_usage = 0
            gpu_usage = 0

        usage = {
            'user': user,
            'docker_status': docker_status,
            'jupyter_status': jupyter_status,
            'disk_usage': 10,  # จำลองไว้ก่อน
            'cpu_usage': cpu_usage,
            'gpu_usage': gpu_usage,
            'updated_at': timezone.now()
        }
        usages.append(usage)

    return render(request, 'core/superuser_dashboard.html', {'usages': usages})

def api_usage_data(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    User = get_user_model()
    users = User.objects.all()
    usage_list = []

    for user in users:
        if not isinstance(user, CustomUser):
            continue

        container = DockerContainer.objects.filter(user=user).first()

        if container:
            stats = get_user_container_stats(container.container_id)
            docker_status = container.status
            jupyter_status = 'running' if container.status == 'running' else 'stopped'
            cpu_usage = stats.get('cpu_percent', 0)
            gpu_usage = stats.get('gpu_percent', 0)
        else:
            docker_status = 'stopped'
            jupyter_status = 'stopped'
            cpu_usage = 0
            gpu_usage = 0

        usage_list.append({
            'username': user.username,
            'docker_status': docker_status,
            'jupyter_status': jupyter_status,
            'disk_usage': 10,
            'cpu_usage': cpu_usage,
            'gpu_usage': gpu_usage,
            'updated_at': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    return JsonResponse({'usages': usage_list})

@login_required
def approve_users(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        try:
            user = CustomUser.objects.get(id=user_id)
            if action == 'approve':
                user.role = user.intended_role
                user.role_verified = True
                user.intended_role = None
            elif action == 'deny':
                user.role = 'bachelor'
                user.role_verified = False
                user.intended_role = None
            user.save()
        except CustomUser.DoesNotExist:
            pass
        return redirect('approve_users')  # name of this view

    pending_users = CustomUser.objects.filter(intended_role__isnull=False)
    return render(request, 'core/approve_users.html', {'pending_users': pending_users})

@login_required
def request_role_verification(request):
    if request.method == 'POST':
        role = request.POST.get('intended_role')
        user = request.user
        user.intended_role = role
        user.role_verified = False  # not verified until approved again
        user.save()
    return redirect('home')