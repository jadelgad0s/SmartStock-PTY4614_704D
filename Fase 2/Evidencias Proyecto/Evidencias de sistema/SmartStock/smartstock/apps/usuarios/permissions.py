"""
Permisos personalizados de DRF.
Implementan el control de acceso basado en el sistema de roles y permisos.
"""
from rest_framework import permissions

from .navegacion import es_administrador, puede_supervisar_bodega


class TienePermiso(permissions.BasePermission):
    """
    Permiso base que verifica si el usuario tiene un permiso específico.
    Se usa como base para permisos específicos.

    Uso:
        class MiPermiso(TienePermiso):
            permiso_requerido = 'crear_producto'
    """
    permiso_requerido = None
    mensaje = 'No tienes permisos para realizar esta acción.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated or not getattr(request.user, 'activo', False):
            return False
        if not self.permiso_requerido:
            return True
        return request.user.tiene_permiso(self.permiso_requerido)


class EsAdministrador(permissions.BasePermission):
    """Solo permite acceso a usuarios con rol administrador."""
    mensaje = 'Solo administradores pueden realizar esta acción.'

    def has_permission(self, request, view):
        return es_administrador(request.user)


class EsEncargadoOAdmin(permissions.BasePermission):
    """Permite acceso a encargados de bodega y administradores."""
    mensaje = 'Requiere rol de encargado de bodega o administrador.'

    def has_permission(self, request, view):
        return puede_supervisar_bodega(request.user)


class PermisoLectura(permissions.BasePermission):
    """
    Requiere el permiso de lectura definido en la vista o acceso de administrador.
    Escritura requiere permiso específico definido en la view.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated or not getattr(request.user, 'activo', False):
            return False
        if request.method in permissions.SAFE_METHODS:
            return es_administrador(request.user) or request.user.tiene_permiso(view.permiso_lectura)
        # Para métodos de escritura, delegamos al permiso específico de la view
        permiso_requerido = getattr(view, 'permiso_requerido', None)
        if permiso_requerido:
            return request.user.tiene_permiso(permiso_requerido)
        return request.user.is_superuser
