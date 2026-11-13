from django.urls import path
from rest_framework.routers import DefaultRouter
from .views_ubicaciones import (EstructuraViewSet, asignaciones_ubicaciones,
                                opciones_ubicaciones, productos_ubicaciones, retirar_asignacion)

router = DefaultRouter()
for recurso in ('pasillos', 'estanterias', 'niveles', 'espacios'):
    router.register(recurso, EstructuraViewSet, basename=recurso)

urlpatterns = [
    path('opciones/', opciones_ubicaciones, name='ubicaciones-opciones'),
    path('productos/', productos_ubicaciones, name='ubicaciones-productos'),
    path('asignaciones/', asignaciones_ubicaciones, name='ubicaciones-asignaciones'),
    path('asignaciones/<int:pk>/', retirar_asignacion, name='ubicaciones-retirar'),
    *router.urls,
]
