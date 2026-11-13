"""Consulta y exportación de auditoría, reservadas a administradores activos."""
import csv
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Case, CharField, F, Max, Q, Value, When
from django.db.models.functions import Concat
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from apps.usuarios.permissions import EsAdministrador
from .models import Auditoria
from .responses import success_response


ACCIONES = dict(Auditoria.ACCION_CHOICES) | {'LOGIN_FAILED': 'Acceso fallido'}
SIN_USUARIO = 'sin_usuario'


class FiltrosAuditoriaSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)
    usuario = serializers.CharField(required=False, allow_blank=True, max_length=30)
    accion = serializers.CharField(required=False, allow_blank=True, max_length=20)
    modelo = serializers.CharField(required=False, allow_blank=True, max_length=100)
    desde = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])
    hasta = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])

    def validate_usuario(self, valor):
        if valor in ('', SIN_USUARIO):
            return valor
        if not valor.isascii() or not valor.isdecimal() or not 0 < int(valor) <= 9223372036854775807:
            raise serializers.ValidationError('Selecciona un usuario válido.')
        return str(int(valor))

    def validate(self, datos):
        if datos.get('desde') and datos.get('hasta') and datos['desde'] > datos['hasta']:
            raise serializers.ValidationError('La fecha inicial no puede ser posterior a la final.')
        # Evita desbordar date al construir el límite superior exclusivo.
        if datos.get('hasta') and datos['hasta'].year == 9999:
            raise serializers.ValidationError({'hasta': 'La fecha debe ser anterior al año 9999.'})
        return datos


class AuditoriaPagination(PageNumberPagination):
    page_size = 25

    def get_paginated_response(self, data):
        respuesta = super().get_paginated_response(data)
        respuesta.data['zona_horaria'] = timezone.get_current_timezone_name()
        return sin_cache(respuesta)


def sin_cache(respuesta):
    respuesta['Cache-Control'] = 'no-store'
    return respuesta


def consulta_base():
    # Antes se usaba DELETE para desactivar y UPDATE para reactivar.
    # Solo se clasifican descripciones inequívocas del módulo correspondiente;
    # se conserva el código original y no se reescriben los eventos históricos.
    reglas = [
        ('DELETE', 'Usuario', 'Usuario desactivado:', 'DEACTIVATE'),
        ('DELETE', 'Producto', 'Producto desactivado:', 'DEACTIVATE'),
        ('DELETE', 'Rol', 'Rol desactivado:', 'DEACTIVATE'),
        ('UPDATE', 'Usuario', 'Usuario reactivado:', 'REACTIVATE'),
        ('UPDATE', 'Producto', 'Producto reactivado:', 'REACTIVATE'),
    ]
    return Auditoria.objects.select_related('usuario').annotate(accion_mostrada=Case(
        *(When(accion__iexact=codigo, modelo__iexact=modelo, descripcion__istartswith=prefijo,
               then=Value(clasificacion)) for codigo, modelo, prefijo, clasificacion in reglas),
        default=F('accion'), output_field=CharField(max_length=20),
    )).order_by('-fecha_creacion', '-id')


def nombre_usuario(evento):
    if evento.usuario_id:
        return evento.usuario.nombre_completo or evento.usuario.email
    return 'Usuario no identificado' if evento.accion == 'LOGIN_FAILED' else 'Usuario no disponible / sistema'


def datos_evento(evento, detalle=False):
    fecha = timezone.localtime(evento.fecha_creacion)
    accion = evento.accion_mostrada
    datos = {
        'id': evento.pk,
        'fecha': fecha.strftime('%d/%m/%Y %H:%M:%S'),
        'fecha_iso': fecha.isoformat(),
        'zona_horaria': timezone.get_current_timezone_name(),
        'usuario_id': evento.usuario_id,
        'usuario': nombre_usuario(evento),
        'usuario_email': evento.usuario.email if evento.usuario_id else '',
        'accion': accion,
        'accion_etiqueta': ACCIONES.get(accion, accion),
        'modelo': evento.modelo,
        'descripcion': evento.descripcion,
    }
    if detalle:
        datos.update(objeto_id=evento.objeto_id, ip_address=evento.ip_address, user_agent=evento.user_agent,
                     accion_registrada=evento.accion)
    return datos


def consulta_filtrada(request):
    filtros = FiltrosAuditoriaSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    datos = filtros.validated_data
    eventos = consulta_base()
    if datos.get('search'):
        texto = datos['search']
        eventos = eventos.annotate(nombre_busqueda=Concat(
            'usuario__nombres', Value(' '), 'usuario__apellidos', output_field=CharField(),
        )).filter(
            Q(nombre_busqueda__icontains=texto) | Q(usuario__email__icontains=texto)
            | Q(descripcion__icontains=texto) | Q(objeto_id__icontains=texto)
        )
    usuario = datos.get('usuario')
    if usuario:
        eventos = eventos.filter(usuario__isnull=True) if usuario == SIN_USUARIO else eventos.filter(usuario_id=usuario)
    for campo in ('accion', 'modelo'):
        if datos.get(campo):
            nombre_campo = 'accion_mostrada' if campo == 'accion' else campo
            eventos = eventos.filter(**{nombre_campo + '__iexact': datos[campo]})
    for campo, lookup, extra in (('desde', 'gte', 0), ('hasta', 'lt', 1)):
        if datos.get(campo):
            dia = datos[campo] + timedelta(days=extra)
            limite = timezone.make_aware(datetime.combine(dia, time.min))
            eventos = eventos.filter(**{'fecha_creacion__' + lookup: limite})
    return eventos, datos


def resumen_filtros(datos):
    filas = []
    if datos.get('search'):
        filas.append(('Búsqueda', datos['search']))
    if datos.get('usuario'):
        usuario = datos['usuario']
        if usuario == SIN_USUARIO:
            etiqueta = 'Sin usuario asociado'
        else:
            persona = get_user_model().objects.filter(pk=usuario).first()
            etiqueta = f'{persona.nombre_completo} ({persona.email})' if persona else f'Usuario #{usuario}'
        filas.append(('Usuario', etiqueta))
    if datos.get('accion'):
        filas.append(('Acción', ACCIONES.get(datos['accion'].upper(), datos['accion'])))
    if datos.get('modelo'):
        filas.append(('Módulo', datos['modelo']))
    for campo, etiqueta in (('desde', 'Desde'), ('hasta', 'Hasta')):
        if datos.get(campo):
            filas.append((etiqueta, datos[campo].strftime('%d/%m/%Y')))
    return filas or [('Filtros', 'Todos los eventos')]


def fijar_reporte(eventos):
    """No incorpora eventos nuevos entre el conteo y la lectura del reporte."""
    ultimo_id = eventos.aggregate(ultimo=Max('id'))['ultimo'] or 0
    return eventos.filter(pk__lte=ultimo_id)


def iterar_eventos(eventos):
    """Lee lotes acotados sin mantener un cursor abierto durante la descarga."""
    ultimo = None
    while True:
        consulta = eventos
        if ultimo is not None:
            consulta = consulta.filter(
                Q(fecha_creacion__lt=ultimo.fecha_creacion)
                | Q(fecha_creacion=ultimo.fecha_creacion, id__lt=ultimo.pk)
            )
        lote = list(consulta[:1000])
        if not lote:
            return
        yield from lote
        ultimo = lote[-1]


@api_view(['GET'])
@permission_classes([IsAuthenticated, EsAdministrador])
def api_auditoria(request):
    """Contrato anterior: los últimos 200 eventos para clientes existentes."""
    data = [{
        'fecha': timezone.localtime(log.fecha_creacion).strftime('%d/%m/%Y %H:%M:%S'),
        'usuario': log.usuario.nombre_completo if log.usuario else 'Sistema',
        'accion': log.accion_mostrada, 'modelo': log.modelo, 'descripcion': log.descripcion,
    } for log in consulta_base()[:200]]
    return sin_cache(success_response(data=data))


@api_view(['GET'])
@permission_classes([IsAuthenticated, EsAdministrador])
def historial_auditoria(request):
    eventos, _ = consulta_filtrada(request)
    paginador = AuditoriaPagination()
    pagina = paginador.paginate_queryset(eventos, request)
    return paginador.get_paginated_response([datos_evento(evento) for evento in pagina])


@api_view(['GET'])
@permission_classes([IsAuthenticated, EsAdministrador])
def detalle_auditoria(request, pk):
    return sin_cache(success_response(data=datos_evento(get_object_or_404(consulta_base(), pk=pk), detalle=True)))


@api_view(['GET'])
@permission_classes([IsAuthenticated, EsAdministrador])
def opciones_auditoria(request):
    eventos = Auditoria.objects.order_by()
    usuarios = get_user_model().objects.filter(
        pk__in=eventos.values('usuario_id'),
    ).order_by('nombres', 'apellidos', 'id')
    modelos = sorted(set(eventos.values_list('modelo', flat=True)), key=str.casefold)
    acciones = sorted(set(ACCIONES) | set(eventos.values_list('accion', flat=True)))
    return sin_cache(success_response(data={
        'usuarios': [{'id': u.pk, 'nombre': u.nombre_completo or u.email, 'email': u.email} for u in usuarios],
        'sin_usuario': eventos.filter(usuario__isnull=True).exists(),
        'modelos': modelos,
        'acciones': [{'valor': a, 'etiqueta': ACCIONES.get(a, a)} for a in acciones],
    }))


class SalidaCSV:
    def write(self, valor):
        return valor


def celda_csv(valor):
    """Evita ejecutar fórmulas al abrir descripciones/correos en una planilla."""
    texto = '' if valor is None else str(valor)
    if texto.lstrip().startswith(('=', '+', '-', '@')) or texto.startswith(('\t', '\r', '\n')):
        return "'" + texto
    return texto


@api_view(['GET'])
@permission_classes([IsAuthenticated, EsAdministrador])
def exportar_auditoria(request):
    eventos, filtros = consulta_filtrada(request)
    eventos = fijar_reporte(eventos)
    total = eventos.count()
    generado = timezone.localtime()
    metadatos = [
        ('Reporte', 'Auditoría del sistema — SmartStock'),
        ('Generado', generado.strftime('%d/%m/%Y %H:%M:%S')),
        ('Zona horaria', timezone.get_current_timezone_name()),
        ('Generado por', request.user.email),
        ('Total de eventos', total),
        *resumen_filtros(filtros),
    ]

    def contenido():
        escritor = csv.writer(SalidaCSV(), delimiter=';')
        yield '\ufeff'
        for fila in metadatos:
            yield escritor.writerow([celda_csv(valor) for valor in fila])
        yield escritor.writerow([])
        yield escritor.writerow(['ID', 'Fecha / hora', 'Zona horaria', 'Usuario', 'Correo', 'Acción',
                                  'Código de acción', 'Módulo', 'Objeto ID', 'Descripción', 'IP', 'Navegador / dispositivo',
                                  'Código registrado'])
        for evento in iterar_eventos(eventos):
            e = datos_evento(evento, detalle=True)
            yield escritor.writerow([celda_csv(e[campo]) for campo in (
                'id', 'fecha', 'zona_horaria', 'usuario', 'usuario_email', 'accion_etiqueta',
                'accion', 'modelo', 'objeto_id', 'descripcion', 'ip_address', 'user_agent', 'accion_registrada',
            )])

    respuesta = StreamingHttpResponse(contenido(), content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = f'attachment; filename="auditoria-{generado:%Y%m%d-%H%M%S}.csv"'
    return sin_cache(respuesta)


@api_view(['GET'])
@permission_classes([IsAuthenticated, EsAdministrador])
def reporte_auditoria(request):
    eventos, filtros = consulta_filtrada(request)
    eventos = fijar_reporte(eventos)
    # El documento tiene su propio diseño de impresión, independiente del ancho del celular.
    html = render_to_string('auditoria_reporte.html', {
        'registros': (datos_evento(evento) for evento in iterar_eventos(eventos)),
        'total': eventos.count(), 'filtros': resumen_filtros(filtros),
        'generado': timezone.localtime().strftime('%d/%m/%Y %H:%M:%S'),
        'zona_horaria': timezone.get_current_timezone_name(), 'generado_por': request.user.email,
    })
    return sin_cache(HttpResponse(html, content_type='text/html; charset=utf-8'))
