"""
Configuración para ambiente de desarrollo local.
"""
from .base import *  # noqa

DEBUG = True

# Permitir cualquier host en desarrollo
ALLOWED_HOSTS = ['*']

# CORS: permitir todo en desarrollo
CORS_ALLOW_ALL_ORIGINS = True

# Email en consola (para pruebas de recuperación de contraseña, etc.)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Logging detallado
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'apps': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
