"""
Views de autenticación: login, logout, refresh, cambio de contraseña.
"""
from django.contrib.auth import login as django_login, logout as django_logout
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings

from apps.core.responses import success_response, error_response
from apps.core.utils import registrar_auditoria
from .navegacion import cuenta_habilitada, inicio_usuario, modulos_usuario
from .serializers import (
    CustomTokenObtainPairSerializer,
    CambioPasswordSerializer,
    UsuarioDetailSerializer,
)


class LoginView(TokenObtainPairView):
    """
    Endpoint de inicio de sesión.

    POST /api/v1/auth/login/
    Body: {"email": "user@example.com", "password": "..."}

    Retorna: access token, refresh token e info del usuario.
    """
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [AllowAny]
    abrir_sesion_web = False

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            # Auditar intento fallido
            email = request.data.get('email', '')
            from .models import Usuario
            usuario_fallido = Usuario.objects.filter(email=email).first()
            registrar_auditoria(
                accion='LOGIN_FAILED',
                modelo='Usuario',
                descripcion=f'Intento fallido de login para: {email}',
                usuario_override=usuario_fallido
            )
            return error_response(
                mensaje='Credenciales incorrectas o cuenta con problemas.',
                errores=serializer.errors if hasattr(serializer, 'errors') else str(e),
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        data = serializer.validated_data
        usuario_login = serializer.user

        if self.abrir_sesion_web:
            django_login(request._request, usuario_login, backend='django.contrib.auth.backends.ModelBackend')
            request.session.set_expiry(api_settings.REFRESH_TOKEN_LIFETIME)

        # Registrar auditoría del login exitoso
        registrar_auditoria(
            accion='LOGIN',
            modelo='Usuario',
            objeto_id=data['usuario']['id'],
            descripcion=f'Inicio de sesión: {data["usuario"]["email"]}',
            usuario_override=usuario_login
        )

        return success_response(
            data=data,
            mensaje='Inicio de sesión exitoso.'
        )


@method_decorator([never_cache, csrf_protect], name='dispatch')
class LoginWebView(LoginView):
    abrir_sesion_web = True


def invalidar_refresh(usuario, refresh):
    token = RefreshToken(refresh)
    if str(token.get(api_settings.USER_ID_CLAIM)) != str(usuario.pk):
        raise TokenError('El token pertenece a otra cuenta.')
    token.blacklist()


def auditar_logout(usuario):
    registrar_auditoria(
        accion='LOGOUT',
        modelo='Usuario',
        objeto_id=usuario.pk,
        descripcion=f'Cierre de sesión: {usuario.email}',
        usuario_override=usuario,
    )


@never_cache
@require_POST
@csrf_protect
def logout_web(request):
    if request.user.is_authenticated:
        refresh = request.POST.get('refresh')
        if refresh:
            try:
                invalidar_refresh(request.user, refresh)
            except TokenError:
                pass
        auditar_logout(request.user)
    django_logout(request)
    return redirect('login_page')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    Endpoint de cierre de sesión.

    POST /api/v1/auth/logout/
    Body: {"refresh": "..."}

    Invalida el refresh token agregándolo a la blacklist.
    """
    try:
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return error_response(
                mensaje='Se requiere el refresh token.',
                status_code=status.HTTP_400_BAD_REQUEST
            )

        invalidar_refresh(request.user, refresh_token)
        auditar_logout(request.user)

        return success_response(mensaje='Sesión cerrada exitosamente.')

    except TokenError:
        return error_response(
            mensaje='Token inválido o expirado.',
            status_code=status.HTTP_400_BAD_REQUEST
        )


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def navegacion_view(request):
    usuario = request.user
    if not cuenta_habilitada(usuario):
        return error_response('Tu cuenta necesita un rol activo. Contacta al administrador.', status_code=403)
    modulos = modulos_usuario(usuario)
    return success_response(data={
        'inicio': inicio_usuario(usuario, modulos),
        'modulos': modulos,
        'usuario': {
            'id': usuario.pk,
            'email': usuario.email,
            'nombre_completo': usuario.nombre_completo,
            'rol': usuario.rol.codigo if usuario.rol_id else None,
            'rol_nombre': usuario.rol.nombre if usuario.rol_id else None,
            'is_superuser': usuario.is_superuser,
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    """
    Retorna los datos del usuario autenticado.

    GET /api/v1/auth/me/
    """
    serializer = UsuarioDetailSerializer(request.user)
    return success_response(data=serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cambiar_password_view(request):
    """
    Endpoint para cambiar la contraseña del usuario autenticado.

    POST /api/v1/auth/cambiar-password/
    Body: {
        "password_actual": "...",
        "password_nueva": "...",
        "password_nueva_confirmacion": "..."
    }
    """
    serializer = CambioPasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            mensaje='Datos inválidos.',
            errores=serializer.errors
        )

    usuario = request.user

    if not usuario.check_password(serializer.validated_data['password_actual']):
        return error_response(
            mensaje='La contraseña actual es incorrecta.',
            status_code=status.HTTP_400_BAD_REQUEST
        )

    usuario.set_password(serializer.validated_data['password_nueva'])
    usuario.save(update_fields=['password'])

    registrar_auditoria(
        accion='UPDATE',
        modelo='Usuario',
        objeto_id=usuario.id,
        descripcion=f'Cambio de contraseña: {usuario.email}'
    )

    return success_response(mensaje='Contraseña actualizada exitosamente.')


class CustomTokenRefreshView(TokenRefreshView):
    """Refresh de token JWT con respuesta estandarizada."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            return success_response(
                data=response.data,
                mensaje='Token renovado.'
            )
        return error_response(
            mensaje='No se pudo renovar el token.',
            status_code=response.status_code
        )
