from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import FileResponse
from django.views.generic import TemplateView

from apps.core.views import (
    login_page, dashboard_page, productos_page, movimientos_page, auditoria_page,
    mermas_page, bodegas_page, transferencias_page, requiere_modulo,
)
from apps.core.views_auditoria import (
    api_auditoria, historial_auditoria, detalle_auditoria,
    opciones_auditoria, exportar_auditoria, reporte_auditoria,
)
from apps.productos.views_alertas_sms import (acceso_sms, opciones_sms, estado_sms, historial_sms,
    detalle_sms, preparar_sms, procesar_sms, cancelar_sms, estado_twilio)
from apps.usuarios.views import usuarios_web_page
from apps.usuarios.views_auth import logout_web
from apps.usuarios.views_recuperacion import (
    SolicitarRecuperacionView, RecuperacionEnviadaView,
    EstablecerNuevaClaveView, ClaveActualizadaView,
)

def favicon_icono(request):
    """Icono del proyecto para clientes que solicitan /favicon.ico."""
    return FileResponse(
        open(settings.BASE_DIR / 'icono.ico', 'rb'),
        content_type='image/x-icon',
    )


urlpatterns = [
    path('favicon.ico', favicon_icono, name='favicon'),
    # === PÁGINAS WEB FRONTEND ===
    path('', login_page, name='login_page'),
    path('contacto/', TemplateView.as_view(template_name='usuarios/contacto.html'), name='contacto_page'),
    path('cerrar-sesion/', logout_web, name='logout_web'),
    path('dashboard/', requiere_modulo(dashboard_page), name='dashboard_page'),
    path('inicio-bodega/', requiere_modulo(TemplateView.as_view(template_name='inicio_bodega.html')), name='inicio_bodega_page'),
    path('productos/', requiere_modulo(productos_page), name='productos_page'),
    path('bodegas/', requiere_modulo(bodegas_page), name='bodegas_page'),
    path('ubicaciones/', requiere_modulo(TemplateView.as_view(template_name='ubicaciones.html')), name='ubicaciones_page'),
    path('alertas-sms/', requiere_modulo(TemplateView.as_view(template_name='alertas_sms.html')), name='alertas_sms_page'),
    path('movimientos/', requiere_modulo(movimientos_page), name='movimientos_page'),
    path('transferencias/', requiere_modulo(transferencias_page), name='transferencias_page'),
    path('mermas/', requiere_modulo(mermas_page), name='mermas_page'),
    path('usuarios/', requiere_modulo(usuarios_web_page), name='usuarios_web_page'),
    path('auditoria/', requiere_modulo(auditoria_page), name='auditoria_page'),
    path('reportes/', requiere_modulo(TemplateView.as_view(template_name='reportes.html')), name='reportes_page'),

    # === RECUPERACIÓN DE CONTRASEÑA ===
    path('recuperar-clave/', SolicitarRecuperacionView.as_view(), name='recuperar_clave'),
    path('recuperacion-enviada/', RecuperacionEnviadaView.as_view(), name='recuperacion_enviada'),
    path('restablecer-clave/<uidb64>/<token>/', EstablecerNuevaClaveView.as_view(), name='establecer_nueva_clave'),
    path('clave-actualizada/', ClaveActualizadaView.as_view(), name='clave_actualizada'),

    # === ADMIN DE DJANGO ===
    path('admin/', admin.site.urls),

    # === API REST v1 ===
    path('api/v1/auth/', include('apps.usuarios.urls_auth')),
    path('api/v1/usuarios/', include('apps.usuarios.urls')),
    path('api/v1/productos/', include('apps.productos.urls')),
    path('api/v1/', include('apps.productos.urls_bodegas')),
    path('api/v1/ubicaciones/', include('apps.productos.urls_ubicaciones')),
    path('api/v1/reportes/', include('apps.productos.urls_reportes')),
    path('api/v1/alertas-sms/estado/', estado_sms, name='sms-estado'),
    path('api/v1/alertas-sms/acceso/', acceso_sms, name='sms-acceso'),
    path('api/v1/alertas-sms/opciones/', opciones_sms, name='sms-opciones'),
    path('api/v1/alertas-sms/preparar/', preparar_sms, name='sms-preparar'),
    path('api/v1/alertas-sms/historial/', historial_sms, name='sms-historial'),
    path('api/v1/alertas-sms/historial/<uuid:envio_id>/', detalle_sms, name='sms-detalle'),
    path('api/v1/alertas-sms/historial/<uuid:envio_id>/cancelar/', cancelar_sms, name='sms-cancelar'),
    path('api/v1/alertas-sms/procesar-pendientes/', procesar_sms, name='sms-procesar'),
    path('api/v1/alertas-sms/twilio/estado/<uuid:envio_id>/', estado_twilio, name='sms-twilio-estado'),
    path('api/v1/auditoria/', api_auditoria, name='api_auditoria'),
    path('api/v1/auditoria/historial/', historial_auditoria, name='historial_auditoria'),
    path('api/v1/auditoria/opciones/', opciones_auditoria, name='opciones_auditoria'),
    path('api/v1/auditoria/exportar/', exportar_auditoria, name='exportar_auditoria'),
    path('api/v1/auditoria/reporte/', reporte_auditoria, name='reporte_auditoria'),
    path('api/v1/auditoria/<int:pk>/', detalle_auditoria, name='detalle_auditoria'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
