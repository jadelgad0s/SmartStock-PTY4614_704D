"""Administración de envíos SMS y recepción autenticada de estados de Twilio."""
import re
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from twilio.request_validator import RequestValidator

from apps.core.responses import error_response, success_response
from apps.core.utils import registrar_auditoria
from apps.usuarios.permissions import EsAdministrador
from .alertas_sms import (
    ESTADOS_TWILIO, PRIORIDAD, callback_url, configuracion_sms,
    procesar_pendientes_sms, telefono_oculto,
)
from .models import EnvioAlertaSMS, LimiteDiarioSMS
from .bodegas import opciones_bodegas
from .views_dashboard import permisos_dashboard
from .views_notificaciones import notificar_administradores


class AdministradorSMS(EsAdministrador):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and (
            request.user.is_superuser or bool(request.user.rol_id and request.user.rol.activo))


class FiltrosSMS(serializers.Serializer):
    estado = serializers.ChoiceField(choices=[''] + [e[0] for e in EnvioAlertaSMS.ESTADOS], required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)
    bodega = serializers.IntegerField(required=False, min_value=1)
    desde = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])
    hasta = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])

    def validate(self, datos):
        if datos.get('desde') and datos.get('hasta') and datos['desde'] > datos['hasta']:
            raise serializers.ValidationError('La fecha inicial no puede ser posterior a la final.')
        if datos.get('hasta') and datos['hasta'].year == 9999:
            raise serializers.ValidationError({'hasta': 'La fecha debe ser anterior al año 9999.'})
        return datos


def filtrar_sms(request):
    filtros = FiltrosSMS(data=request.query_params.dict())
    filtros.is_valid(raise_exception=True)
    datos = filtros.validated_data
    qs = EnvioAlertaSMS.objects.all()
    if datos.get('estado'):
        qs = qs.filter(estado=datos['estado'])
    if datos.get('bodega'):
        qs = qs.filter(bodega_id=datos['bodega'])
    if datos.get('search'):
        texto = datos['search']
        qs = qs.filter(Q(sku__icontains=texto) | Q(producto_nombre__icontains=texto)
                       | Q(bodega_nombre__icontains=texto) | Q(codigo_error__icontains=texto))
    for campo, lookup, extra in (('desde', 'gte', 0), ('hasta', 'lt', 1)):
        if datos.get(campo):
            dia = datos[campo] + timedelta(days=extra)
            qs = qs.filter(**{'fecha_creacion__' + lookup: timezone.make_aware(datetime.combine(dia, time.min))})
    return qs.order_by('-fecha_creacion', '-id'), datos


def situacion_sms():
    configuracion = configuracion_sms()
    usados = LimiteDiarioSMS.objects.filter(fecha=timezone.localdate()).values_list('intentos', flat=True).first() or 0
    return configuracion, usados, max(0, settings.SMS_ALERTAS_LIMITE_DIARIO - usados)


def pendientes_revisables(qs=None):
    if qs is None:
        qs = EnvioAlertaSMS.objects.all()
    return qs.filter(estado='PENDIENTE', intentos__lt=3).filter(
        Q(twilio_sid__isnull=True) | Q(twilio_sid='')).exclude(proximo_intento__gt=timezone.now())


def datos_sms(e, configuracion, disponibles, *, detalle=False):
    motivo = ''
    if e.estado == 'PENDIENTE':
        if e.twilio_sid:
            motivo = 'Ya tiene un identificador de Twilio. Revisa el resultado antes de cualquier reenvío.'
        elif e.intentos >= 3:
            motivo = 'Alcanzó el máximo de 3 intentos; requiere revisión.'
        elif e.proximo_intento and e.proximo_intento > timezone.now():
            motivo = 'Espera hasta la próxima revisión indicada.'
        elif not configuracion['activa']:
            motivo = 'Los envíos SMS están pausados en el servidor.'
        elif not configuracion['lista']:
            motivo = 'La configuración SMS está incompleta.'
        elif disponibles <= 0:
            motivo = 'Se alcanzó el límite diario de intentos.'
        else:
            motivo = 'Disponible para revisar; se comprobará que la alerta siga vigente.'
    elif e.estado in ('INCIERTO', 'ENVIANDO'):
        motivo = 'Espera o revisa el resultado en Twilio. Este aviso no se reenvía desde la pantalla.'
    procesable = bool(e.estado == 'PENDIENTE' and not e.twilio_sid and e.intentos < 3
                     and (not e.proximo_intento or e.proximo_intento <= timezone.now())
                     and configuracion['activa'] and configuracion['lista'] and disponibles > 0)
    datos = {
        'id': str(e.pk), 'sku': e.sku, 'producto': e.producto_nombre,
        'bodega': e.bodega_nombre, 'bodega_id': e.bodega_id, 'stock': e.cantidad, 'minimo': e.minimo,
        'nivel': 'bajo' if e.nivel == 1 else 'agotado', 'destinatario': telefono_oculto(e.destinatario),
        'estado': e.estado, 'estado_etiqueta': e.get_estado_display(), 'intentos': e.intentos,
        'twilio_sid': e.twilio_sid, 'codigo_error': e.codigo_error, 'detalle': e.detalle,
        'fecha': e.fecha_creacion, 'ultima_actualizacion': e.fecha_modificacion,
        'ultimo_intento': e.ultimo_intento, 'proximo_intento': e.proximo_intento,
        'motivo': motivo, 'procesable': procesable,
        'cancelable': e.estado == 'PENDIENTE' and not e.twilio_sid,
    }
    if detalle:
        datos['mensaje'] = e.mensaje
    return datos


class DatosProcesamiento(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), max_length=3, min_length=1, required=False)

    def validate(self, datos):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError('Solo se permite seleccionar hasta 3 avisos por revisión.')
        if 'ids' in datos and len(set(datos['ids'])) != len(datos['ids']):
            raise serializers.ValidationError({'ids': 'No repitas un aviso dentro del lote.'})
        return datos


@transaction.atomic
def registrar_solicitud_sms(request, seleccion):
    ids = ', '.join(str(e.pk) for e in seleccion)
    registrar_auditoria(accion='UPDATE', modelo='EnvioAlertaSMS', usuario_override=request.user,
                       descripcion=f'Solicitud de revisión de {len(seleccion)} avisos SMS. IDs: {ids}.')
    notificar_administradores(tipo='OTRO', titulo='Revisión de SMS solicitada',
                             mensaje=f'Se solicitó revisar {len(seleccion)} avisos SMS. Consulta el historial para conocer sus resultados.',
                             link='/alertas-sms/', actor_id=request.user.pk)


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def acceso_sms(request):
    permitido = bool(AdministradorSMS().has_permission(request, None))
    return success_response({'ver': permitido, 'procesar': permitido})


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated, AdministradorSMS])
def opciones_sms(request):
    return success_response({'bodegas': opciones_bodegas(incluir_inactivas=True), 'estados': [
        {'valor': v, 'etiqueta': e} for v, e in EnvioAlertaSMS.ESTADOS], 'menu': permisos_dashboard(request.user)})


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated, AdministradorSMS])
def estado_sms(request):
    configuracion, usados, disponibles = situacion_sms()
    return success_response(data={
        'activa': configuracion['activa'], 'configurada': configuracion['lista'],
        'errores_configuracion': configuracion['errores'],
        'destinatarios': [telefono_oculto(t) for t in configuracion['destinatarios']],
        'limite_diario': settings.SMS_ALERTAS_LIMITE_DIARIO, 'intentos_hoy': usados,
        'zona_horaria': settings.TIME_ZONE,
        'pendientes': EnvioAlertaSMS.objects.filter(estado='PENDIENTE').count(),
        'por_confirmar': EnvioAlertaSMS.objects.filter(estado__in=['INCIERTO', 'ENVIANDO']).count(),
        'revisables': pendientes_revisables().count(), 'cuota_disponible': disponibles,
        'esperando': EnvioAlertaSMS.objects.filter(estado='PENDIENTE', proximo_intento__gt=timezone.now()).count(),
        'lote_maximo': 3,
    })


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated, AdministradorSMS])
def historial_sms(request):
    registros, _ = filtrar_sms(request)
    configuracion, _, disponibles = situacion_sms()
    paginador = PageNumberPagination()
    paginador.page_size = 25
    pagina = paginador.paginate_queryset(registros, request)
    respuesta = paginador.get_paginated_response([datos_sms(e, configuracion, disponibles) for e in pagina])
    respuesta.data['zona_horaria'] = settings.TIME_ZONE
    respuesta.data['revisables'] = pendientes_revisables(registros).count()
    return respuesta


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated, AdministradorSMS])
def detalle_sms(request, envio_id):
    configuracion, _, disponibles = situacion_sms()
    return success_response(datos_sms(get_object_or_404(EnvioAlertaSMS, pk=envio_id), configuracion, disponibles, detalle=True))


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated, AdministradorSMS])
def preparar_sms(request):
    qs, datos = filtrar_sms(request)
    if datos.get('estado') not in ('', None, 'PENDIENTE'):
        return error_response('Selecciona Pendientes o Todos los estados para preparar una revisión.')
    configuracion, _, disponibles = situacion_sms()
    lista = list(pendientes_revisables(qs).order_by('fecha_creacion', 'id')[:min(3, disponibles)]) if configuracion['activa'] and configuracion['lista'] else []
    return success_response({'envios': [datos_sms(e, configuracion, disponibles, detalle=True) for e in lista],
                             'lote_maximo': 3, 'cuota_disponible': disponibles})


@never_cache
@api_view(['POST'])
@permission_classes([IsAuthenticated, AdministradorSMS])
def procesar_sms(request):
    seleccionador = DatosProcesamiento(data=request.data)
    seleccionador.is_valid(raise_exception=True)
    configuracion = configuracion_sms()
    if not configuracion['activa'] or not configuracion['lista']:
        return error_response('Activa y completa la configuración SMS en el servidor.', status_code=409)
    _, _, disponibles = situacion_sms()
    if not disponibles:
        return error_response('Se alcanzó el límite diario de intentos. Actualiza el estado del servicio.', status_code=409)
    ids = seleccionador.validated_data.get('ids')
    if ids is None:
        ids = list(pendientes_revisables().order_by('fecha_creacion', 'id').values_list('pk', flat=True)[:3])
    seleccion = list(EnvioAlertaSMS.objects.filter(pk__in=ids).order_by('fecha_creacion', 'id'))
    if len(seleccion) != len(ids):
        return error_response('Alguno de los avisos seleccionados ya no está disponible. Actualiza el historial.', status_code=404)
    if seleccion:
        # Confirmar la solicitud antes de abrir la red. Ninguna transacción
        # exterior puede revertir una reserva después de que Twilio la acepte.
        registrar_solicitud_sms(request, seleccion)
    cantidad = procesar_pendientes_sms(envio_ids=ids)
    configuracion, _, disponibles = situacion_sms()
    return success_response(data={'revisados': cantidad, 'resultados': [
        datos_sms(e, configuracion, disponibles, detalle=True) for e in EnvioAlertaSMS.objects.filter(pk__in=ids).order_by('fecha_creacion', 'id')
    ]}, mensaje='Revisión completada. Aceptado por Twilio todavía no significa entregado al celular.')


@never_cache
@api_view(['POST'])
@permission_classes([IsAuthenticated, AdministradorSMS])
@transaction.atomic
def cancelar_sms(request, envio_id):
    if request.data:
        return error_response('Esta operación no permite cambiar el mensaje ni el estado manualmente.')
    envio = get_object_or_404(EnvioAlertaSMS.objects.select_for_update(), pk=envio_id)
    if envio.estado == 'CANCELADO':
        return success_response(mensaje='El aviso ya estaba cancelado.')
    if envio.estado != 'PENDIENTE' or envio.twilio_sid:
        return error_response('El aviso ya cambió de estado y no se puede cancelar desde la cola. Actualiza el historial.', status_code=409)
    envio.estado = 'CANCELADO'
    envio.detalle = 'Cancelado por un administrador desde Alertas SMS.'
    envio.save(update_fields=['estado', 'detalle', 'fecha_modificacion'])
    registrar_auditoria(accion='UPDATE', modelo='EnvioAlertaSMS', objeto_id=str(envio.pk), usuario_override=request.user,
                       descripcion=f'Aviso SMS cancelado: {envio.sku}, {envio.bodega_nombre}, destinatario {telefono_oculto(envio.destinatario)}.')
    notificar_administradores(tipo='OTRO', titulo='Aviso SMS cancelado',
                             mensaje=f'Se canceló el aviso pendiente de {envio.producto_nombre} en {envio.bodega_nombre}.',
                             link='/alertas-sms/', actor_id=request.user.pk)
    return success_response(mensaje='Aviso cancelado. Se conserva su historial.')


@never_cache
@csrf_exempt
@require_POST
def estado_twilio(request, envio_id):
    """No usa JWT: valida la firma oficial sobre la URL HTTPS pública exacta."""
    if not settings.TWILIO_AUTH_TOKEN or request.content_type != 'application/x-www-form-urlencoded':
        return HttpResponse(status=403)
    firma = request.headers.get('X-Twilio-Signature', '')
    valido = RequestValidator(settings.TWILIO_AUTH_TOKEN).validate(callback_url(envio_id), request.POST, firma)
    if not valido or request.POST.get('AccountSid') != settings.TWILIO_ACCOUNT_SID:
        return HttpResponse(status=403)
    sid = request.POST.get('MessageSid', '')
    destino = ESTADOS_TWILIO.get(request.POST.get('MessageStatus', ''))
    if not re.fullmatch(r'SM[0-9a-fA-F]{32}', sid) or destino is None:
        return HttpResponse(status=400)
    with transaction.atomic():
        envio = EnvioAlertaSMS.objects.select_for_update().filter(pk=envio_id).first()
        if envio is None:
            return HttpResponse(status=404)
        if (envio.intentos == 0 or (envio.twilio_sid and envio.twilio_sid != sid)
                or (request.POST.get('To') and request.POST['To'] != envio.destinatario)):
            return HttpResponse(status=409)
        envio.twilio_sid = sid
        if PRIORIDAD[destino] > PRIORIDAD[envio.estado]:
            envio.estado = destino
            codigo = request.POST.get('ErrorCode', '')
            envio.codigo_error = codigo if re.fullmatch(r'[0-9]{1,12}', codigo) else ''
            envio.detalle = '' if destino not in ('NO_ENTREGADO', 'RECHAZADO') else 'Twilio informó un fallo de entrega; consulta el código de error.'
        elif destino == envio.estado and re.fullmatch(r'[0-9]{1,12}', request.POST.get('ErrorCode', '')):
            envio.codigo_error = request.POST['ErrorCode']
        envio.save(update_fields=['twilio_sid', 'estado', 'codigo_error', 'detalle', 'fecha_modificacion'])
    return HttpResponse(status=204)
