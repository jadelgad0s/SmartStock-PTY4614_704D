"""
Utilidades comunes del sistema.
"""
from .models import Auditoria
from .middleware import get_current_user, get_current_request, get_client_ip


def registrar_auditoria(accion, modelo, objeto_id='', descripcion='', usuario_override=None):
    """
    Registra una acción en el log de auditoría.

    Args:
        accion: Tipo de acción (CREATE, UPDATE, DEACTIVATE, REACTIVATE, DELETE, LOGIN, etc.)
        modelo: Nombre del modelo afectado
        objeto_id: ID del objeto sobre el que se realizó la acción
        descripcion: Descripción libre del evento
    """
    request = get_current_request()
    usuario = usuario_override if usuario_override else get_current_user()

    ip_address = None
    user_agent = ''

    if request:
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

    Auditoria.objects.create(
        usuario=usuario,
        accion=accion,
        modelo=modelo,
        objeto_id=str(objeto_id),
        descripcion=descripcion,
        ip_address=ip_address,
        user_agent=user_agent,
    )

