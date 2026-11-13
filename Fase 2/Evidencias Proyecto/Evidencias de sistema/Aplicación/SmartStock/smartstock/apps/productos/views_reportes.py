"""Consulta, CSV e impresión autenticados de reportes de inventario."""
import csv
import io
from tempfile import SpooledTemporaryFile

from django.http import FileResponse, HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.cache import never_cache
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination

from apps.core.responses import success_response
from .bodegas import opciones_bodegas
from .models import Producto
from .reportes import PlanReporte, ZONA, busqueda_producto, lectura_consistente
from .views_dashboard import permisos_dashboard


def capacidades(usuario):
    activo = usuario.is_authenticated and usuario.activo and (usuario.is_superuser or bool(usuario.rol_id and usuario.rol.activo))
    ver = bool(activo and usuario.tiene_permiso('ver_reportes'))
    return {'ver': ver, 'exportar': bool(ver and usuario.tiene_permiso('exportar_reportes'))}


class PuedeVerReportes(permissions.BasePermission):
    message = 'No tienes permiso para consultar reportes de inventario.'

    def has_permission(self, request, view):
        return capacidades(request.user)['ver']


class PuedeExportarReportes(PuedeVerReportes):
    message = 'No tienes permiso para exportar o imprimir reportes.'

    def has_permission(self, request, view):
        return capacidades(request.user)['exportar']


class ReportePagination(PageNumberPagination):
    page_size = 25


@never_cache
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def acceso_reportes(request):
    return success_response(data=capacidades(request.user))


@never_cache
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, PuedeVerReportes])
def opciones_reportes(request):
    return success_response(data={'bodegas': opciones_bodegas(incluir_inactivas=True),
                                  'permisos': capacidades(request.user), 'menu': permisos_dashboard(request.user)})


@never_cache
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, PuedeVerReportes])
def productos_reportes(request):
    texto = serializers.CharField(max_length=200, allow_blank=True).run_validation(request.query_params.get('search', ''))
    qs = busqueda_producto(Producto.objects.all(), texto).order_by('nombre', 'id')
    paginador = ReportePagination()
    pagina = paginador.paginate_queryset(qs, request)
    return paginador.get_paginated_response([{'id': p.pk, 'sku': p.sku, 'nombre': p.nombre, 'activo': p.activo} for p in pagina])


@never_cache
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, PuedeVerReportes])
def consultar_reporte(request):
    with lectura_consistente():
        plan = PlanReporte(request.query_params)
        paginador = ReportePagination()
        pagina = paginador.paginate_queryset(plan.qs, request)
        respuesta = paginador.get_paginated_response(list(plan.filas(pagina, pagina=True)))
        respuesta.data['meta'] = {**plan.metadatos(), 'permisos': capacidades(request.user)}
        return respuesta


def celda_csv(valor):
    # Los números se conservan numéricos; solo los textos pueden introducir fórmulas.
    if isinstance(valor, (int, float)):
        return valor
    texto = '' if valor is None else str(valor)
    return "'" + texto if texto.lstrip().startswith(('=', '+', '-', '@')) or texto.startswith(('\t', '\r', '\n')) else texto


@never_cache
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, PuedeExportarReportes])
def exportar_reporte(request):
    archivo = SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode='w+b')
    try:
        with lectura_consistente():
            plan = PlanReporte(request.query_params)
            meta = plan.metadatos()
            texto = io.TextIOWrapper(archivo, encoding='utf-8-sig', newline='')
            escritor = csv.writer(texto, delimiter=';')
            for fila in [('Reporte', meta['titulo']), ('Generado', meta['generado']), ('Zona horaria', str(ZONA)),
                         ('Generado por', request.user.email), ('Total de registros', plan.qs.count()),
                         *meta['filtros'], *[(r['etiqueta'], r['valor']) for r in meta['resumen']],
                         *[('Nota', n) for n in meta['notas']]]:
                escritor.writerow([celda_csv(v) for v in fila])
            escritor.writerow([])
            escritor.writerow([c['etiqueta'] for c in plan.columnas])
            for fila in plan.filas(plan.iterar()):
                escritor.writerow([celda_csv(fila[c['campo']]) for c in plan.columnas])
            texto.flush()
            texto.detach()
        archivo.seek(0)
        return FileResponse(archivo, as_attachment=True, filename=f'smartstock-{plan.informe}-{plan.ahora:%Y%m%d-%H%M%S}.csv', content_type='text/csv; charset=utf-8')
    except BaseException:
        archivo.close()
        raise


@never_cache
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, PuedeExportarReportes])
def imprimir_reporte(request):
    with lectura_consistente():
        plan = PlanReporte(request.query_params)
        total = plan.qs.count()
        if total > 10000:
            raise serializers.ValidationError('El documento supera 10.000 registros. Acota los filtros o descarga el CSV completo.')
        registros = ([fila[c['campo']] for c in plan.columnas] for fila in plan.filas(plan.iterar()))
        html = render_to_string('inventario_reporte.html', {
            'meta': plan.metadatos(), 'total': total, 'registros': registros, 'generado_por': request.user.email,
        })
        return HttpResponse(html, content_type='text/html; charset=utf-8')
