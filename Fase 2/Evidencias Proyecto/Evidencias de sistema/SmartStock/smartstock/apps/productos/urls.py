"""
URLs del módulo de productos.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Importamos todas las vistas que hemos creado
from .views import ProductoViewSet
from .views_consulta_codigos import consultar_codigo
from .views_dashboard import resumen_dashboard, alertas_dashboard, inicio_bodega
from .views_movimientos import (
    registrar_movimiento, ultimos_movimientos, historial_movimientos,
    detalle_movimiento, resolver_producto_movimiento,
)
from .views_mermas import mermas_api, historial_mermas, detalle_merma, productos_merma
from .views_transferencias import (
    transferencias_api, opciones_transferencias, productos_transferencias,
    resolver_transferencia, detalle_transferencia,
)
from .views_notificaciones import (
    notificaciones_no_leidas, marcar_notificacion_leida, marcar_todas_leidas,
)

router = DefaultRouter()
router.register(r'', ProductoViewSet, basename='producto')

urlpatterns = [
    path('consultar-codigo/', consultar_codigo, name='producto-consultar-codigo'),
    path('notificaciones/no-leidas/', notificaciones_no_leidas, name='notif-no-leidas'),
    path('notificaciones/<int:pk>/marcar-leida/', marcar_notificacion_leida, name='notif-marcar-leida'),
    path('notificaciones/marcar-todas-leidas/', marcar_todas_leidas, name='notif-marcar-todas'),
    path('mermas/', mermas_api, name='mermas-api'),
    path('mermas/historial/', historial_mermas, name='historial-mermas'),
    path('mermas/productos/', productos_merma, name='productos-merma'),
    path('mermas/<int:pk>/', detalle_merma, name='detalle-merma'),
    path('transferencias/', transferencias_api, name='transferencias-api'),
    path('transferencias/opciones/', opciones_transferencias, name='transferencias-opciones'),
    path('transferencias/productos/', productos_transferencias, name='transferencias-productos'),
    path('transferencias/resolver/', resolver_transferencia, name='transferencias-resolver'),
    path('transferencias/<int:pk>/', detalle_transferencia, name='transferencia-detalle'),
    # Nuestras rutas personalizadas
    path('inicio-bodega/', inicio_bodega, name='inicio-bodega-datos'),
    path('dashboard-resumen/', resumen_dashboard, name='dashboard-resumen'),
    path('dashboard-alertas/', alertas_dashboard, name='dashboard-alertas'),
    path('ultimos-movimientos/', ultimos_movimientos, name='ultimos-movimientos'),
    path('registrar-movimiento/', registrar_movimiento, name='registrar-movimiento'),
    path('resolver-movimiento/', resolver_producto_movimiento, name='resolver-movimiento'),
    path('movimientos/', historial_movimientos, name='historial-movimientos'),
    path('movimientos/<int:pk>/', detalle_movimiento, name='detalle-movimiento'),
    
    # Rutas por defecto del CRUD de productos
    path('', include(router.urls)),
]

