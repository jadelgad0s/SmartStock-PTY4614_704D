from django.urls import path
from .views_reportes import (
    acceso_reportes, opciones_reportes, productos_reportes,
    consultar_reporte, exportar_reporte, imprimir_reporte,
)

urlpatterns = [
    path('acceso/', acceso_reportes, name='reportes-acceso'),
    path('opciones/', opciones_reportes, name='reportes-opciones'),
    path('productos/', productos_reportes, name='reportes-productos'),
    path('consulta/', consultar_reporte, name='reportes-consulta'),
    path('exportar/', exportar_reporte, name='reportes-exportar'),
    path('imprimir/', imprimir_reporte, name='reportes-imprimir'),
]
