import os
import shutil
from django.conf import settings
from users.models import CustomUser

def get_user_workspace(user):
    """Returns the absolute path to user's workspace in format User_<ID>_(<USERNAME>)"""
    return os.path.join(settings.MEDIA_ROOT, f'User_{user.id}_({user.username})')

def ensure_workspace_exists(user):
    """Creates user workspace if it doesn't exist with the new naming format"""
    workspace = get_user_workspace(user)
    if not os.path.exists(workspace):
        os.makedirs(workspace)
    return workspace