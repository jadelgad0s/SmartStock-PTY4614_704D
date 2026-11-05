"""Avisos internos de las operaciones de SmartStock.

Los endpoints solo permiten leer o modificar las notificaciones del usuario.
"""
from django.db import transaction, models
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.core.responses import success_response, error_response
from apps.usuarios.models import Usuario
from .models import Notificacion


@transaction.atomic
def notificar_administradores(*, tipo, titulo, mensaje, link, actor_id=None):
    """Un aviso por administrador activo y para quien realiza la operación.

    Los llamadores guardan operación, auditoría y avisos en una transacción:
    un cambio rechazado nunca aparece como realizado en la campana.
    """
    destinatarios = Usuario.objects.filter(activo=True).filter(
        models.Q(is_superuser=True) | models.Q(rol__codigo='administrador') |
        models.Q(pk=actor_id)
    ).values_list('id', flat=True).distinct()
    Notificacion.objects.bulk_create([
        Notificacion(usuario_destino_id=id_usuario, tipo=tipo,
                     titulo=titulo[:150], mensaje=mensaje, link=link[:200])
        for id_usuario in destinatarios
    ])



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notificaciones_no_leidas(request):
    if not request.user.activo:
        return error_response('Cuenta desactivada.', status_code=status.HTTP_403_FORBIDDEN)
    qs = Notificacion.objects.filter(
        usuario_destino=request.user, leida=False,
    ).order_by('-fecha_creacion', '-id')
    total = qs.count()
    items = [{
        'id': n.id, 'tipo': n.tipo, 'titulo': n.titulo, 'mensaje': n.mensaje,
        'link': n.link,
        'fecha': timezone.localtime(n.fecha_creacion).strftime('%d/%m %H:%M'),
    } for n in qs[:20]]
    return success_response(data={'items': items, 'total': total})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def marcar_notificacion_leida(request, pk):
    if not request.user.activo:
        return error_response('Cuenta desactivada.', status_code=status.HTTP_403_FORBIDDEN)
    actualizadas = Notificacion.objects.filter(
        pk=pk, usuario_destino=request.user, leida=False,
    ).update(leida=True)
    if not actualizadas:
        return error_response('Notificación inexistente o ya leída.', status_code=status.HTTP_404_NOT_FOUND)
    return success_response(mensaje='Notificación marcada como leída.')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def marcar_todas_leidas(request):
    if not request.user.activo:
        return error_response('Cuenta desactivada.', status_code=status.HTTP_403_FORBIDDEN)
    cantidad = Notificacion.objects.filter(
        usuario_destino=request.user, leida=False,
    ).update(leida=True)
    return success_response(data={'actualizadas': cantidad})

