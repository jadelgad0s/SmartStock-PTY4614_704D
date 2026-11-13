"""
Managers y QuerySets adicionales para el módulo de usuarios.
"""
from django.db import models


class UsuarioActivoManager(models.Manager):
    """Manager que devuelve solo usuarios activos."""

    def get_queryset(self):
        return super().get_queryset().filter(activo=True)
