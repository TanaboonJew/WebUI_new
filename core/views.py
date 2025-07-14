from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import FileResponse, Http404, HttpResponseForbidden
from .docker_utils import docker_manager, manage_container
from .file_utils import ensure_workspace_exists
from .models import DockerContainer, UserFile, AIModel, CustomUser, ContainerSchedule
from .forms import DockerfileUploadForm, FileUploadForm, AIModelForm, DockerImageForm
from .monitoring import get_system_stats, get_user_container_stats
from django.contrib import messages
from django.conf import settings
from collections import defaultdict
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from .decorators import role_verified_required
import os
import docker
from django.utils.dateparse import parse_datetime
from datetime import datetime
from .scheduler import reload_schedules
from datetime import timedelta
from django.db.models import Q


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

    
@role_verified_required
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

@role_verified_required
@login_required
def start_container_view(request):
    user = request.user
    container = DockerContainer.objects.filter(user=user).last()
    if container and not container.can_user_start:
        messages.error(request, "Admin has disabled your ability to start the container.")
        return redirect('docker-management')

    success = docker_manager.manage_container(user, action='start', container_type='jupyter')
    if success:
        messages.success(request, "Container started successfully.")
    else:
        messages.error(request, "Failed to start container.")
    return redirect('docker-management')

@role_verified_required
@login_required
def stop_container_view(request):
    user = request.user
    success = manage_container(user, action='stop', container_type='jupyter') 
    if success:
        messages.success(request, "Container stopped successfully.")
    else:
        messages.warning(request, "Could not stop container.")
    return redirect('docker-management')

@role_verified_required
@login_required
def delete_container_view(request):
    if request.method == 'POST':
        success = docker_manager.manage_container(request.user, action='delete', container_type='jupyter')
        if success:
            messages.success(request, "Container deleted successfully.")
        else:
            messages.error(request, "Failed to delete container.")
    return redirect('docker-management')

@role_verified_required
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

@role_verified_required
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
        print("DEBUG stats['disk'] before:", stats.get('disk'))
        if stats and 'disk' in stats:
            try:
                disk_percent = float(stats['disk'].get('percent', 0))
            except (ValueError, TypeError):
                disk_percent = 0
            stats['disk']['free_percent'] = round(100 - disk_percent, 1)
            print("DEBUG stats['disk'] after:", stats['disk'])

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
    system_stats = get_system_stats()
    container_stats = None
    
    container = DockerContainer.objects.filter(user=request.user).first()
    if container:
        container_stats = get_user_container_stats(container.container_id)

        if container_stats:
            # Normalize CPU percent by user's cpu_limit if available
            cpu_raw = container_stats.get('cpu_percent')
            user_cpu_limit = getattr(request.user, 'cpu_limit', 1)
            if cpu_raw is not None and user_cpu_limit > 0:
                container_stats['cpu_percent'] = round(cpu_raw / user_cpu_limit, 2)
            else:
                container_stats['cpu_percent'] = 0

            # Calculate memory usage percentage
            memory_usage = container_stats.get('memory_usage', 0)
            memory_limit = container_stats.get('memory_limit', 0)
            if memory_limit and memory_limit > 0:
                memory_percent = (memory_usage / memory_limit) * 100
            else:
                memory_percent = 0
            container_stats['memory_percent'] = round(memory_percent, 2)
    
    return render(request, 'core/private_dashboard.html', {
        'system_stats': system_stats,
        'container_stats': container_stats,
        'user': request.user,
        'container': container
    })

@role_verified_required
@login_required
def ai_dashboard(request):
    models = AIModel.objects.filter(user=request.user)
    form = AIModelForm()

    user_container = DockerContainer.objects.filter(user=request.user).first()
    jupyter_token = None
    jupyter_url = None
    container_status = None

    if user_container:
        try:
            container_name = f"jupyter_{request.user.id}_{request.user.username}"
            container = docker_manager.client.containers.get(container_name)
            real_status = container.status 

            if user_container.status != real_status:
                user_container.status = real_status
                user_container.save()

            container_status = real_status 

            if real_status == 'running':
                jupyter_url = f"http://{settings.SERVER_IP}:{user_container.jupyter_port}/?token={user_container.jupyter_token}"
                jupyter_token = user_container.jupyter_token

        except docker.errors.NotFound:
            container_status = 'not_found' 
            if user_container:
                user_container.delete()
            user_container = None  

    else:
        container_status = 'not_found' 

    if request.method == 'POST':
        if not request.user.is_accessible:
            messages.error(request, "Not available at this time")
            return redirect('ai-dashboard')
        
        if 'start_jupyter' in request.POST:
            framework = request.POST.get('framework', '').strip().lower()
            if not framework:
                db_container = DockerContainer.objects.filter(user=request.user).first()
                if db_container and db_container.framework:
                    framework = db_container.framework
                else:
                    framework = 'tensorflow'

            image_map = {
                'tensorflow': 'my-tf',
                'pytorch': 'my-torch',
            }

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

                user_container = DockerContainer.objects.filter(user=request.user).first()
                if user_container:
                    user_container.jupyter_token = jupyter_token or ''
                    user_container.status = 'running'
                    user_container.framework = framework
                    user_container.save()

                messages.success(request, f"Jupyter Notebook started! Token: {jupyter_token or 'N/A'}")
            else:
                messages.error(request, "Failed to start Jupyter Notebook")

            return redirect('ai-dashboard')

        elif 'stop_jupyter' in request.POST:
            result = docker_manager.manage_container(request.user, 'stop', container_type='jupyter')
            if result:
                messages.success(request, "Jupyter Notebook stopped successfully")
            else:
                messages.error(request, "Failed to stop Jupyter Notebook")
                print("Stop failed even though container might be stopped. Check logs.")
            return redirect('ai-dashboard')

        elif 'delete_jupyter' in request.POST:
            if docker_manager.manage_container(request.user, 'delete', container_type='jupyter'):
                messages.success(request, "Jupyter Notebook container deleted successfully")
                container_status = None
            else:
                messages.error(request, "Failed to delete Jupyter Notebook container")
            return redirect('ai-dashboard')

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
                
    now = timezone.now()
    schedules = ContainerSchedule.objects.filter(
        active=True
    ).filter(
        Q(start_datetime__lte=now, end_datetime__gte=now) |
        Q(start_datetime__gt=now)
    ).order_by('start_datetime').select_related('container', 'container__user')

    def format_timedelta(td):
        total_seconds = int(td.total_seconds())
        if total_seconds <= 0:
            return "0s"
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0:
            parts.append(f"{seconds}s")
        return ' '.join(parts)

    schedule_with_remaining = []
    for s in schedules:
        if s.start_datetime > now:
            remaining = s.start_datetime - now
            is_upcoming = True
            time_until_end = None
            remaining_str = format_timedelta(remaining)
            time_until_end_str = None
        else:
            remaining = timedelta(seconds=0)
            is_upcoming = False
            time_until_end = s.end_datetime - now
            if time_until_end.total_seconds() < 0:
                time_until_end = timedelta(seconds=0)
            time_until_end_str = format_timedelta(time_until_end)
            remaining_str = None

        schedule_with_remaining.append({
            'schedule': s,
            'remaining_str': remaining_str,
            'is_upcoming': is_upcoming,
            'time_until_end_str': time_until_end_str,
        })

    return render(request, 'core/ai_dashboard.html', {
        'models': models,
        'form': form,
        'jupyter_token': jupyter_token,
        'jupyter_url': jupyter_url,
        'container_status': container_status,
        'container': user_container,
        'upcoming_schedules': schedule_with_remaining,
    })

@role_verified_required
@login_required
def delete_model(request, model_id):
    try:
        model = AIModel.objects.get(id=model_id, user=request.user)
        model.delete()
        messages.success(request, "Model deleted successfully")
    except AIModel.DoesNotExist:
        messages.error(request, "Model not found")
    return redirect('ai-dashboard')

@role_verified_required
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



@login_required
def superuser_dashboard(request):
    if not request.user.is_superuser:
        return redirect('home')

    User = get_user_model()
    users = User.objects.all()
    usages = []

    MAX_GPU_MEMORY_MB = 81559 

    for user in users:
        if not isinstance(user, CustomUser):
            continue

        container = DockerContainer.objects.filter(user=user).first()

        if container:
            stats = get_user_container_stats(container.container_id)
            docker_status = container.status
            jupyter_status = 'running' if container.status == 'running' else 'stopped'
            cpu_usage = stats.get('cpu_percent', 0)
            memory_usage = stats.get('memory_usage', 0)  # in bytes
            gpu_memory_mb = stats.get('gpu_memory_mb', 0)
            gpu_memory_percent = (gpu_memory_mb / MAX_GPU_MEMORY_MB) * 100 if MAX_GPU_MEMORY_MB > 0 else 0
        else:
            docker_status = 'stopped'
            jupyter_status = 'stopped'
            cpu_usage = 0
            memory_usage = 0
            gpu_memory_mb = 0
            gpu_memory_percent = 0

        # Convert RAM usage to MB
        mem_limit_mb = user.mem_limit  # already in MB
        used_ram_mb = round(memory_usage / (1024 * 1024), 2)
        ram_usage_percent = round((used_ram_mb / mem_limit_mb) * 100, 1) if mem_limit_mb > 0 else 0
        
        disk_usage_str = "N/A"
        if container and container.status == 'running':
            try:
                result = container.exec_run("du -sh /", user="root")
                print(f"Exec run exit code: {result.exit_code}")
                print(f"Exec run output: {result.output.decode()}")
                if result.exit_code == 0:
                    disk_usage_str = result.output.decode().strip().split()[0]
                else:
                    print(f"du command failed with exit code {result.exit_code}")
            except Exception as e:
                print(f"[Disk] Error for {container.container_id}: {e}")


        usage = {
            'user': user,
            'docker_status': docker_status,
            'jupyter_status': jupyter_status,
            'cpu_usage': cpu_usage,
            'gpu_memory_mb': gpu_memory_mb,
            'gpu_memory_percent': gpu_memory_percent,
            'used_ram_mb': used_ram_mb,
            'ram_limit_mb': mem_limit_mb,
            'ram_usage_percent': ram_usage_percent,
            'updated_at': timezone.now(),
            'container': container,
            'disk_usage': disk_usage_str,
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
            gpu_mem_used = stats.get('gpu_memory_used_mb', 0)
            gpu_usage = round((gpu_mem_used / 80000) * 100, 2)
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
    if not request.user.is_superuser:
        return redirect('home')
    
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
                user.role = 'None'
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
        
        valid_roles = [choice[0] for choice in CustomUser.ROLE_CHOICES if choice[0] != 'none']
        if role not in valid_roles:
            messages.error(request, "บทบาทที่ขอไม่ถูกต้อง")
            return redirect('home')
        
        user = request.user
        user.intended_role = role
        user.role_verified = False  # not verified until approved again
        user.save()
        messages.success(request, "ส่งคำขอยืนยันตัวตนสำเร็จ")
    return redirect('home')

@login_required
def allocate_resources(request, user_id):
    if not request.user.is_superuser:
        return HttpResponseForbidden("You are not authorized to access this page.")

    user = get_object_or_404(CustomUser, id=user_id)

    MAX_RAM_MB = 256 * 1024
    MAX_CPU_CORES = 64

    if request.method == 'POST':
        mem_limit = request.POST.get('mem_limit')
        memswap_limit = request.POST.get('memswap_limit')
        cpu_limit = request.POST.get('cpu_limit')
        gpu_access = request.POST.get('gpu_access') == 'on'

        try:
            mem_limit_int = int(mem_limit)
            memswap_limit_int = int(memswap_limit)
            cpu_limit_int = int(cpu_limit)

            if memswap_limit_int < mem_limit_int:
                return render(request, 'core/allocate_resources.html', {
                    'user_obj': user,
                    'error': 'RAM Swap Limit ต้องไม่น้อยกว่า RAM Limit'
                })

            if mem_limit_int > MAX_RAM_MB:
                return render(request, 'core/allocate_resources.html', {
                    'user_obj': user,
                    'error': 'RAM Limit ต้องไม่เกิน 256 GB'
                })

            if cpu_limit_int > MAX_CPU_CORES:
                return render(request, 'core/allocate_resources.html', {
                    'user_obj': user,
                    'error': 'CPU Limit ต้องไม่เกิน 64 cores'
                })

            user.mem_limit = mem_limit_int
            user.memswap_limit = memswap_limit_int
            user.cpu_limit = cpu_limit_int
            user.gpu_access = gpu_access
            user.save()
            return redirect('superuser-dashboard')

        except ValueError as e:
            return render(request, 'core/allocate_resources.html', {
                'user_obj': user,
                'error': 'Invalid input. Please enter numbers only.'
            })

    return render(request, 'core/allocate_resources.html', {'user_obj': user})

@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def admin_start_container_view(request, container_id):
    container = get_object_or_404(DockerContainer, id=container_id)
    success = docker_manager.manage_container(container.user, action='start', container_type='jupyter')
    if success:
        container.status = 'running'
        container.can_user_start = True
        container.save()
        messages.success(request, "Started container.")
    else:
        messages.error(request, "Failed to start container.")
    return redirect('superuser-dashboard')


@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_POST
def admin_stop_container_view(request, container_id):
    container = get_object_or_404(DockerContainer, id=container_id)
    success = docker_manager.manage_container(container.user, action='stop', container_type='jupyter', by_admin=True)
    if success:
        container.status = 'stopped'
        container.can_user_start = False
        container.save()
        messages.success(request, "Stopped container.")
    else:
        messages.error(request, "Failed to stop container.")
    return redirect('superuser-dashboard')

@staff_member_required
def create_schedule(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    container = DockerContainer.objects.filter(user=user).first()

    if not container:
        return render(request, 'core/schedule_form.html', {'error': 'User has no container.'})

    if request.method == 'POST':
        start_date = request.POST['start_date']
        start_time = request.POST['start_time']
        end_date = request.POST['end_date']
        end_time = request.POST['end_time']
        active = 'active' in request.POST

        start_dt_str = f"{start_date} {start_time}"
        end_dt_str = f"{end_date} {end_time}"

        start_dt = datetime.strptime(start_dt_str, "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(end_dt_str, "%Y-%m-%d %H:%M")

        ContainerSchedule.objects.update_or_create(
            container=container,
            defaults={
                'start_datetime': start_dt,
                'end_datetime': end_dt,
                'active': active,
            }
        )
        
        # เรียก reload scheduler job ใหม่
        reload_schedules()

        return redirect('superuser-dashboard')

    existing_schedule = container.schedules.first()

    return render(request, 'core/schedule_form.html', {
        'user': user,
        'container': container,
        'schedule': existing_schedule,
    })