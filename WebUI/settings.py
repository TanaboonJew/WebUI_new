import os
from pathlib import Path

# === BASE DIRECTORY ===
BASE_DIR = Path(__file__).resolve().parent.parent

# === SECURITY ===
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-dev-key-only')  # Replace with real secret in production
DEBUG = True  # WARNING: Set to False in production
ALLOWED_HOSTS = ['*']  # Accept connections from all hosts — restrict this in production
SERVER_IP = '192.168.0.100'  # LAN IP of your host machine for dynamic Jupyter URLs

# === APPLICATION DEFINITIONS ===
INSTALLED_APPS = [
    # Core
    'daphne',  # ASGI server
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # 3rd-party
    'channels',  # Django Channels (WebSocket support)
    'crispy_forms',  # For crispy form rendering
    'crispy_bootstrap5',  # Bootstrap 5 theme for crispy forms

    # Custom apps
    'users',  # Custom user model
    'core',   # Your main business logic
    
    'background_task',
]

# === MIDDLEWARE STACK ===
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# === URL CONFIGURATION ===
ROOT_URLCONF = 'WebUI.urls'

# === TEMPLATE CONFIGURATION ===
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],  # Global templates directory
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',  # Required by Django Admin
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# === WSGI / ASGI ===
WSGI_APPLICATION = 'WebUI.wsgi.application'
ASGI_APPLICATION = 'WebUI.asgi.application'

# === DATABASE ===
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',  # Use PostgreSQL in production
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# === AUTHENTICATION ===
AUTH_USER_MODEL = 'users.CustomUser'  # Custom user model
LOGIN_REDIRECT_URL = 'home'  # After login
LOGOUT_REDIRECT_URL = 'home'  # After logout

# === PASSWORD VALIDATION ===
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# === LOCALIZATION ===
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

# === STATIC FILES ===
STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]  # Dev-time static files
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')  # Where collectstatic puts files

# === MEDIA FILES (User uploads) ===
MEDIA_URL = '/user-files/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'user_data')

# === CRISPY FORMS ===
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# === CHANNELS (WebSocket layer) ===
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],  # Redis must be running locally
        },
    },
}

# === CUSTOM DIRECTORIES FOR WORKSPACE ===
# Ensure folders exist at runtime for container mounting
os.makedirs(MEDIA_ROOT, exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'jupyter_notebooks'), exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'docker_volumes'), exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'ai_models'), exist_ok=True)
