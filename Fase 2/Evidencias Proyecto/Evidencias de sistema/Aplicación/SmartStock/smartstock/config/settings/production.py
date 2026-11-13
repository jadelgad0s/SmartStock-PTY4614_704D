
"""
Configuración de producción de SmartStock.
Despliegue en Render con PostgreSQL en Neon.
"""

import os
import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from decouple import config
from .base import *

# === SEGURIDAD ===
DEBUG = False

ALLOWED_HOSTS = [
    "smartstockchile.cl",
    "www.smartstockchile.cl",
]

# Agregar automáticamente el dominio temporal de Render
render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

if render_hostname:
    ALLOWED_HOSTS.append(render_hostname)

CSRF_TRUSTED_ORIGINS = [
    "https://smartstockchile.cl",
    "https://www.smartstockchile.cl",
]

if render_hostname:
    CSRF_TRUSTED_ORIGINS.append(
        f"https://{render_hostname}"
    )

# HTTPS detrás del proxy de Render
SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Activaremos HSTS después de probar el dominio
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# === BASE DE DATOS EN NEON ===
DATABASE_URL = config("DATABASE_URL", default="")

if not DATABASE_URL:
    raise ImproperlyConfigured(
        "Falta configurar DATABASE_URL en producción."
    )

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=0,
        ssl_require=True,
    )
}

# === ARCHIVOS ESTÁTICOS ===
STATIC_URL = "/static/"

MIDDLEWARE.insert(
    MIDDLEWARE.index(
        "django.middleware.security.SecurityMiddleware"
    ) + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

STORAGES = {
    "default": {
        "BACKEND": (
            "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage."
            "CompressedManifestStaticFilesStorage"
        ),
    },
}

# === CORREOS DE RECUPERACIÓN POR API HTTPS ===
# SMTP no está disponible en servicios Render Free. Los emails se envían
# por un proveedor HTTPS y requieren remitente verificado en ese proveedor.
EMAIL_BACKEND = 'apps.usuarios.email_backends.ResendEmailBackend'
RESEND_API_KEY = config('RESEND_API_KEY', default='')

