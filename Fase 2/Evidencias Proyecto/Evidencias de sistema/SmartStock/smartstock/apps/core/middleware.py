"""
Middleware personalizado para SmartStock.
"""
import threading

# Storage local por thread para hacer el request accesible desde señales
_thread_locals = threading.local()


def get_current_request():
    """Obtiene el request actual desde cualquier parte del código."""
    return getattr(_thread_locals, 'request', None)


def get_current_user():
    """Obtiene el usuario autenticado actual."""
    request = get_current_request()
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        return request.user
    return None


class AuditMiddleware:
    """
    Middleware que hace disponible el request actual en cualquier
    parte del código. Necesario para que las señales de auditoría
    puedan capturar el usuario que realizó la acción.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.request = request
        response = self.get_response(request)
        # Limpiar después del request para evitar leaks entre requests
        if hasattr(_thread_locals, 'request'):
            del _thread_locals.request
        return response


def get_client_ip(request):
    """Obtiene la IP real del cliente considerando proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')
