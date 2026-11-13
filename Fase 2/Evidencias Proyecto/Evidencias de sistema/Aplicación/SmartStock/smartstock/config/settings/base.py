"""
Configuración base de SmartStock.
Este archivo contiene los settings comunes a todos los ambientes.
Los ambientes específicos (development.py, production.py) heredan de aquí.
"""
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

# === PATHS ===
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# === SEGURIDAD ===
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# === APLICACIONES ===
DJANGO_APPS = [
    'apps.usuarios.admin_config.SmartStockAdminConfig',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
]

LOCAL_APPS = [
    'apps.core',
    'apps.usuarios',
    'apps.productos',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# === MIDDLEWARE ===
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.AuditMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# === BASE DE DATOS ===
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='smartstock'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600,
    }
}

# === MODELO DE USUARIO CUSTOM ===
AUTH_USER_MODEL = 'usuarios.Usuario'

# === VALIDACIÓN DE CONTRASEÑAS ===
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# === INTERNACIONALIZACIÓN ===
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

# === ARCHIVOS ESTÁTICOS Y MEDIA ===
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# === DJANGO REST FRAMEWORK ===
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.usuarios.authentication.JWTConRolActivo',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
}

# === JWT ===
SIMPLE_JWT = {
    'USER_AUTHENTICATION_RULE': 'apps.usuarios.navegacion.cuenta_habilitada',
    'ACCESS_TOKEN_LIFETIME': timedelta(
        minutes=config('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', default=60, cast=int)
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        days=config('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7, cast=int)
    ),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    # Un cambio de contraseña invalida los JWT emitidos previamente.
    'CHECK_REVOKE_TOKEN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# === RECUPERACIÓN DE CONTRASEÑAS ===
# Tokens Django de un solo uso; expiran en 1 hora y se invalidan al cambiar la clave.
PASSWORD_RESET_TIMEOUT = 60 * 60
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='SmartStock <no-reply@smartstockchile.cl>')

# === CORS ===
CORS_ALLOW_CREDENTIALS = True

# === ALERTAS DE STOCK POR SMS (Twilio, servicio con costo) ===
SMS_ALERTAS_ACTIVAS = config('SMS_ALERTAS_ACTIVAS', default=True, cast=bool)
SMS_ALERTAS_DESTINATARIOS = config('SMS_ALERTAS_DESTINATARIOS', default='', cast=Csv())
SMS_ALERTAS_LIMITE_DIARIO = config('SMS_ALERTAS_LIMITE_DIARIO', default=100, cast=int)
SMS_ALERTAS_TIMEOUT = config('SMS_ALERTAS_TIMEOUT', default=3, cast=int)
TWILIO_ACCOUNT_SID = config('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = config('TWILIO_AUTH_TOKEN', default='')
TWILIO_MESSAGING_SERVICE_SID = config('TWILIO_MESSAGING_SERVICE_SID', default='')
TWILIO_FROM_NUMBER = config('TWILIO_FROM_NUMBER', default='')
TWILIO_PUBLIC_BASE_URL = config('TWILIO_PUBLIC_BASE_URL', default='https://smartstockchile.cl')

