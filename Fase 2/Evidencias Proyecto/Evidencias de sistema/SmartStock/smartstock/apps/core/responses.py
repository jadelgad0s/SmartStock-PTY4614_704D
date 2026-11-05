"""
Respuestas API estandarizadas.
Todas las respuestas de la API siguen el mismo formato para consistencia.
"""
from rest_framework.response import Response
from rest_framework import status


def success_response(data=None, mensaje='Operación exitosa', status_code=status.HTTP_200_OK):
    """Respuesta exitosa estándar."""
    return Response({
        'success': True,
        'mensaje': mensaje,
        'data': data,
    }, status=status_code)


def error_response(mensaje='Ocurrió un error', errores=None, status_code=status.HTTP_400_BAD_REQUEST):
    """Respuesta de error estándar."""
    return Response({
        'success': False,
        'mensaje': mensaje,
        'errores': errores,
    }, status=status_code)
