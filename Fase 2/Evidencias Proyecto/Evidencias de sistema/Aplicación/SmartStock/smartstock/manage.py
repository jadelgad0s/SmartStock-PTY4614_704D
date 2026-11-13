#!/usr/bin/env python
"""Utilidad de administración de Django para SmartStock."""
import os
import sys


def main():
    """Punto de entrada para comandos administrativos."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. ¿Está instalado y disponible en tu "
            "PYTHONPATH? ¿Olvidaste activar el entorno virtual?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
