"""
URLs del módulo de usuarios.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import UsuarioViewSet, RolViewSet, PermisoViewSet

router = DefaultRouter()
router.register(r'', UsuarioViewSet, basename='usuario')

roles_router = DefaultRouter()
roles_router.register(r'', RolViewSet, basename='rol')

permisos_router = DefaultRouter()
permisos_router.register(r'', PermisoViewSet, basename='permiso')

urlpatterns = [
    path('roles/', include(roles_router.urls)),
    path('permisos/', include(permisos_router.urls)),
    path('', include(router.urls)),
]
