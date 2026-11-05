"""
Views del módulo de usuarios: CRUD de usuarios, roles y permisos.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth.password_validation import password_validators_help_texts
from django.db.models import Q
from django.db import IntegrityError, transaction
from apps.core.safe_delete import tiene_relaciones

from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from rest_framework import viewsets, status
from rest_framework.decorators import action

from apps.core.responses import success_response, error_response
from apps.core.utils import registrar_auditoria
from apps.productos.views_notificaciones import notificar_administradores
from .models import Usuario, Rol, Permiso
from .serializers import (
    UsuarioListSerializer,
    UsuarioDetailSerializer,
    UsuarioCreateSerializer,
    UsuarioUpdateSerializer,
    RolSerializer,
    PermisoSerializer,
)
from .permissions import EsAdministrador


def es_cuenta_administradora(usuario):
    return usuario.cuenta_protegida


class UsuariosPagination(PageNumberPagination):
    page_size = 25


class UsuarioViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de usuarios.

    Endpoints:
        GET    /api/v1/usuarios/           Lista de usuarios
        POST   /api/v1/usuarios/           Crear usuario
        GET    /api/v1/usuarios/{id}/      Detalle de usuario
        PUT    /api/v1/usuarios/{id}/      Actualizar usuario
        PATCH  /api/v1/usuarios/{id}/      Actualizar parcial
        DELETE /api/v1/usuarios/{id}/      Desactivar (soft delete)
        POST   /api/v1/usuarios/{id}/activar/    Reactivar usuario
        POST   /api/v1/usuarios/{id}/resetear-password/    Resetear contraseña
    """
    queryset = Usuario.objects.select_related('rol').all()
    permission_classes = [IsAuthenticated, EsAdministrador]
    pagination_class = UsuariosPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['activo', 'rol']
    search_fields = ['email', 'nombres', 'apellidos']
    ordering_fields = ['fecha_creacion', 'nombres', 'apellidos', 'email', 'ultimo_login', 'id']
    ordering = ['nombres', 'apellidos', 'id']

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action in ('update', 'partial_update', 'destroy', 'activar', 'eliminar_definitivamente', 'resetear_password'):
            # Solo se bloquea el usuario: el rol nullable se obtiene con un JOIN.
            queryset = queryset.select_for_update(of=('self',), no_key=self.action != 'eliminar_definitivamente')
        return queryset

    def notificar_cambio(self, usuario, titulo, resultado):
        notificar_administradores(
            tipo='OTRO', titulo=titulo,
            mensaje=f'Usuario «{usuario.nombre_completo}» ({usuario.email}): {resultado}.',
            link='/usuarios/', actor_id=self.request.user.pk,
        )

    @action(detail=False, methods=['get'])
    def opciones(self, request):
        """Roles para filtros/formularios y requisitos reales de contraseña."""
        roles = Rol.objects.order_by('nombre', 'id').values('id', 'nombre', 'codigo', 'descripcion', 'activo')
        return success_response(data={
            'roles': list(roles), 'password_requisitos': password_validators_help_texts(),
        })

    def get_serializer_class(self):
        if self.action == 'create':
            return UsuarioCreateSerializer
        elif self.action in ('update', 'partial_update'):
            return UsuarioUpdateSerializer
        elif self.action == 'list':
            return UsuarioListSerializer
        return UsuarioDetailSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return success_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                mensaje='Datos inválidos.',
                errores=serializer.errors
            )

        try:
            with transaction.atomic():
                usuario = serializer.save()
                registrar_auditoria(
                    accion='CREATE', modelo='Usuario', objeto_id=usuario.id,
                    descripcion=f'Usuario creado: {usuario.email}',
                )
                self.notificar_cambio(usuario, 'Usuario creado', 'cuenta creada correctamente')
        except IntegrityError:
            if Usuario.objects.filter(email__iexact=serializer.validated_data['email']).exists():
                return error_response(mensaje='Datos inválidos.', errores={
                    'email': ['Ya existe un usuario con este correo.'],
                })
            raise

        return success_response(
            data=UsuarioDetailSerializer(usuario).data,
            mensaje='Usuario creado exitosamente.',
            status_code=status.HTTP_201_CREATED
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        # No se permite degradar ni promover una cuenta administrativa desde el CRUD.
        if es_cuenta_administradora(instance) and 'rol_id' in request.data:
            nuevo_rol = str(request.data.get('rol_id'))
            if nuevo_rol != str(instance.rol_id):
                return error_response(
                    mensaje='No puedes cambiar el rol de una cuenta administradora.',
                    status_code=status.HTTP_403_FORBIDDEN,
                )
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if not serializer.is_valid():
            return error_response(
                mensaje='Datos inválidos.',
                errores=serializer.errors
            )

        usuario = serializer.save()

        registrar_auditoria(
            accion='UPDATE',
            modelo='Usuario',
            objeto_id=usuario.id,
            descripcion=f'Usuario actualizado: {usuario.email}'
        )
        self.notificar_cambio(usuario, 'Usuario actualizado', 'datos actualizados correctamente')

        return success_response(
            data=UsuarioDetailSerializer(usuario).data,
            mensaje='Usuario actualizado exitosamente.'
        )

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """Desactivación (soft delete) del usuario."""
        instance = self.get_object()

        if instance == request.user:
            return error_response(
                mensaje='No puedes desactivar tu propia cuenta.',
                status_code=status.HTTP_400_BAD_REQUEST
            )
        if es_cuenta_administradora(instance):
            return error_response(
                mensaje='No se pueden desactivar cuentas administradoras.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not instance.activo:
            return success_response(mensaje='El usuario ya estaba desactivado.')
        instance.desactivar()

        registrar_auditoria(
            accion='DEACTIVATE',
            modelo='Usuario',
            objeto_id=instance.id,
            descripcion=f'Usuario desactivado: {instance.email}'
        )
        self.notificar_cambio(instance, 'Usuario desactivado', 'cuenta desactivada')

        return success_response(mensaje='Usuario desactivado exitosamente.')

    @action(detail=True, methods=['delete'], url_path='eliminar-definitivamente')
    @transaction.atomic
    def eliminar_definitivamente(self, request, pk=None):
        """Nunca eliminar administradores, cuenta propia o usuarios con historial."""
        usuario = self.get_object()
        if usuario.pk == request.user.pk or es_cuenta_administradora(usuario):
            return error_response(
                mensaje='No se puede eliminar la cuenta propia ni cuentas administradoras.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if tiene_relaciones(usuario):
            return error_response(
                mensaje='El usuario tiene historial asociado; solo puedes desactivarlo.',
                status_code=status.HTTP_409_CONFLICT,
            )
        identificador, correo = usuario.id, usuario.email
        usuario.delete()
        registrar_auditoria(
            accion='DELETE', modelo='Usuario', objeto_id=identificador,
            descripcion=f'Usuario eliminado definitivamente: {correo}',
        )
        self.notificar_cambio(usuario, 'Usuario eliminado', 'cuenta eliminada definitivamente')
        return success_response(mensaje='Usuario eliminado definitivamente.')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def activar(self, request, pk=None):
        """Reactiva un usuario previamente desactivado."""
        usuario = self.get_object()
        if usuario.activo:
            return success_response(data=UsuarioDetailSerializer(usuario).data, mensaje='El usuario ya estaba activo.')
        usuario.activar()

        registrar_auditoria(
            accion='REACTIVATE',
            modelo='Usuario',
            objeto_id=usuario.id,
            descripcion=f'Usuario reactivado: {usuario.email}'
        )
        self.notificar_cambio(usuario, 'Usuario reactivado', 'cuenta reactivada')

        return success_response(
            data=UsuarioDetailSerializer(usuario).data,
            mensaje='Usuario reactivado exitosamente.'
        )

    @action(detail=True, methods=['post'], url_path='resetear-password')
    @transaction.atomic
    def resetear_password(self, request, pk=None):
        """
        Resetea la contraseña de un usuario.
        Body: {"password_nueva": "..."}
        """
        usuario = self.get_object()
        password_nueva = request.data.get('password_nueva')

        if not password_nueva or len(password_nueva) < 8:
            return error_response(
                mensaje='La contraseña debe tener al menos 8 caracteres.'
            )

        usuario.set_password(password_nueva)
        # También desbloquear si estaba bloqueado
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.save(update_fields=['password', 'intentos_fallidos', 'bloqueado_hasta'])

        registrar_auditoria(
            accion='UPDATE',
            modelo='Usuario',
            objeto_id=usuario.id,
            descripcion=f'Contraseña reseteada por admin: {usuario.email}'
        )
        self.notificar_cambio(usuario, 'Contraseña restablecida', 'contraseña restablecida por administración')

        return success_response(mensaje='Contraseña reseteada exitosamente.')


class RolViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de roles.

    Los roles marcados como 'es_sistema=True' no pueden ser eliminados.
    """
    queryset = Rol.objects.prefetch_related('permisos').all()
    serializer_class = RolSerializer
    permission_classes = [IsAuthenticated, EsAdministrador]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['activo', 'es_sistema']
    search_fields = ['nombre', 'codigo']
    ordering = ['nombre']

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(mensaje='Datos inválidos.', errores=serializer.errors)

        rol = serializer.save()
        registrar_auditoria(
            accion='CREATE',
            modelo='Rol',
            objeto_id=rol.id,
            descripcion=f'Rol creado: {rol.nombre}'
        )
        return success_response(
            data=self.get_serializer(rol).data,
            mensaje='Rol creado exitosamente.',
            status_code=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if not serializer.is_valid():
            return error_response(mensaje='Datos inválidos.', errores=serializer.errors)

        rol = serializer.save()
        registrar_auditoria(
            accion='UPDATE',
            modelo='Rol',
            objeto_id=rol.id,
            descripcion=f'Rol actualizado: {rol.nombre}'
        )
        return success_response(
            data=self.get_serializer(rol).data,
            mensaje='Rol actualizado exitosamente.'
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.es_sistema:
            return error_response(
                mensaje='No se pueden eliminar roles de sistema.',
                status_code=status.HTTP_400_BAD_REQUEST
            )

        if instance.usuarios.filter(activo=True).exists():
            return error_response(
                mensaje='No se puede eliminar un rol que tiene usuarios asignados.',
                status_code=status.HTTP_400_BAD_REQUEST
            )

        instance.desactivar()
        registrar_auditoria(
            accion='DEACTIVATE',
            modelo='Rol',
            objeto_id=instance.id,
            descripcion=f'Rol desactivado: {instance.nombre}'
        )
        return success_response(mensaje='Rol desactivado exitosamente.')


class PermisoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet de solo lectura para permisos.
    Los permisos se crean vía seeders, no vía API.
    """
    queryset = Permiso.objects.all()
    serializer_class = PermisoSerializer
    permission_classes = [IsAuthenticated, EsAdministrador]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['modulo']
    search_fields = ['codigo', 'nombre']
    ordering = ['modulo', 'codigo']

    from django.shortcuts import render
from django.contrib.auth.decorators import login_required

def usuarios_web_page(request):
    # Renderizo la pantalla HTML de gestión de usuarios que consume nuestra API
    return render(request, 'usuarios/listar.html')

