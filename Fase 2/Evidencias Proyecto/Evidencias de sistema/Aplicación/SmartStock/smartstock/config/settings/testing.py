"""Pruebas aisladas: SQLite por defecto o PostgreSQL local/CI explícito.

No utiliza DATABASE_URL ni las credenciales de producción de la aplicación.
"""
import os
os.environ.setdefault('SECRET_KEY', 'smartstock-isolated-testing-key-not-for-production')
from .base import *

SECRET_KEY = 'smartstock-isolated-testing-key-not-for-production'
DEBUG = False
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
SMS_ALERTAS_ACTIVAS = False
SMS_ALERTAS_DESTINATARIOS = []

if os.environ.get('SS_TEST_POSTGRES', '').lower() in ('1', 'true'):
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('SS_TEST_DB_NAME', 'smartstock_pruebas'),
        'USER': os.environ.get('SS_TEST_DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('SS_TEST_DB_PASSWORD', ''),
        'HOST': os.environ.get('SS_TEST_DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('SS_TEST_DB_PORT', '5432'),
        'CONN_MAX_AGE': 0,
        'OPTIONS': {'options': '-c lock_timeout=10000 -c statement_timeout=30000'},
    }}
else:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
