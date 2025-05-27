import os
from django.conf import settings

def get_user_workspace(user):
    """Returns the absolute path to user's workspace in format user_<ID>_<username>"""
    return os.path.join(settings.MEDIA_ROOT, f'user_{user.id}_{user.username}')

def ensure_workspace_exists(user):
    """Creates user workspace if it doesn't exist"""
    workspace = get_user_workspace(user)
    if not os.path.exists(workspace):
        os.makedirs(workspace)
    return workspace
