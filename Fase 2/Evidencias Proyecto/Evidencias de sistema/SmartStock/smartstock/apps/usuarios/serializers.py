"""
Serializers del módulo de usuarios.
"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import Usuario, Rol, Permiso
from .navegacion import cuenta_habilitada, inicio_usuario


class PermisoSerializer(serializers.ModelSerializer):
    """Serializer de permisos."""

    class Meta:
        model = Permiso
        fields = ('id', 'codigo', 'nombre', 'descripcion', 'modulo')
        read_only_fields = ('id',)


class RolSerializer(serializers.ModelSerializer):
    """Serializer de roles con sus permisos."""
    permisos = PermisoSerializer(many=True, read_only=True)
    permisos_ids = serializers.PrimaryKeyRelatedField(
        queryset=Permiso.objects.all(),
        many=True,
        write_only=True,
        required=False,
        source='permisos'
    )
    cantidad_usuarios = serializers.SerializerMethodField()

    class Meta:
        model = Rol
        fields = (
            'id', 'nombre', 'codigo', 'descripcion',
            'permisos', 'permisos_ids', 'es_sistema',
            'activo', 'cantidad_usuarios',
            'fecha_creacion', 'fecha_modificacion'
        )
        read_only_fields = ('id', 'es_sistema', 'fecha_creacion', 'fecha_modificacion')

    def get_cantidad_usuarios(self, obj):
        return obj.usuarios.filter(activo=True).count()


class UsuarioListSerializer(serializers.ModelSerializer):
    """Serializer para listar usuarios (versión resumida)."""
    rol_nombre = serializers.CharField(source='rol.nombre', read_only=True)
    nombre_completo = serializers.CharField(read_only=True)
    cuenta_protegida = serializers.BooleanField(read_only=True)

    class Meta:
        model = Usuario
        fields = (
            'id', 'email', 'nombres', 'apellidos', 'nombre_completo',
            'rol', 'rol_nombre', 'telefono', 'activo', 'is_superuser',
            'ultimo_login', 'fecha_creacion', 'cuenta_protegida'
        )
        read_only_fields = ('id', 'ultimo_login', 'fecha_creacion')


class UsuarioDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado de un usuario."""
    rol = RolSerializer(read_only=True)
    rol_id = serializers.PrimaryKeyRelatedField(
        queryset=Rol.objects.filter(activo=True),
        source='rol',
        write_only=True,
        required=False,
        allow_null=True
    )
    nombre_completo = serializers.CharField(read_only=True)
    cuenta_protegida = serializers.BooleanField(read_only=True)

    class Meta:
        model = Usuario
        fields = (
            'id', 'email', 'nombres', 'apellidos', 'nombre_completo',
            'rol', 'rol_id', 'telefono', 'activo',
            'ultimo_login', 'fecha_creacion', 'fecha_modificacion', 'cuenta_protegida', 'is_superuser'
        )
        read_only_fields = ('id', 'ultimo_login', 'fecha_creacion', 'fecha_modificacion', 'is_superuser')


class UsuarioCreateSerializer(serializers.ModelSerializer):
    """Serializer para crear usuarios."""
    password = serializers.CharField(
        write_only=True,
        required=True,
        trim_whitespace=False,
        style={'input_type': 'password'}
    )
    password_confirmacion = serializers.CharField(
        write_only=True,
        required=True,
        trim_whitespace=False,
        style={'input_type': 'password'}
    )
    rol_id = serializers.PrimaryKeyRelatedField(
        queryset=Rol.objects.filter(activo=True),
        source='rol',
        required=True
    )

    class Meta:
        model = Usuario
        fields = (
            'email', 'nombres', 'apellidos', 'telefono',
            'rol_id', 'password', 'password_confirmacion'
        )

    def validate_email(self, value):
        """Valida que el email no esté ya registrado."""
        if Usuario.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Ya existe un usuario con este email.')
        return value.lower()

    def validate(self, attrs):
        """Valida que las contraseñas coincidan y cumplan requisitos."""
        password = attrs.get('password')
        password_confirmacion = attrs.pop('password_confirmacion', None)

        if password != password_confirmacion:
            raise serializers.ValidationError({
                'password_confirmacion': 'Las contraseñas no coinciden.'
            })

        try:
            validate_password(password, user=Usuario(
                email=attrs.get('email', ''), nombres=attrs.get('nombres', ''), apellidos=attrs.get('apellidos', ''),
            ))
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})

        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        usuario = Usuario.objects.create_user(password=password, **validated_data)
        return usuario


class UsuarioUpdateSerializer(serializers.ModelSerializer):
    """Serializer para actualizar usuarios (sin contraseña)."""
    rol_id = serializers.PrimaryKeyRelatedField(
        queryset=Rol.objects.filter(activo=True),
        source='rol',
        required=False,
        allow_null=True
    )

    class Meta:
        model = Usuario
        fields = ('nombres', 'apellidos', 'telefono', 'rol_id')


class CambioPasswordSerializer(serializers.Serializer):
    """Serializer para cambiar contraseña."""
    password_actual = serializers.CharField(
        required=True,
        style={'input_type': 'password'}
    )
    password_nueva = serializers.CharField(
        required=True,
        style={'input_type': 'password'}
    )
    password_nueva_confirmacion = serializers.CharField(
        required=True,
        style={'input_type': 'password'}
    )

    def validate(self, attrs):
        if attrs['password_nueva'] != attrs['password_nueva_confirmacion']:
            raise serializers.ValidationError({
                'password_nueva_confirmacion': 'Las contraseñas no coinciden.'
            })

        try:
            validate_password(attrs['password_nueva'])
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password_nueva': list(e.messages)})

        return attrs


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializer personalizado para login.
    Valida cuenta activa, cuenta bloqueada y agrega info del usuario al token.
    """
    username_field = 'email'

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Datos adicionales en el token
        token['email'] = user.email
        token['nombre_completo'] = user.nombre_completo
        token['rol'] = user.rol.codigo if user.rol else None
        return token

    def validate(self, attrs):
        email = attrs.get('email', '').lower()
        password = attrs.get('password')

        # Buscar usuario primero para validaciones específicas
        try:
            usuario = Usuario.objects.get(email=email)
        except Usuario.DoesNotExist:
            raise serializers.ValidationError({
                'detail': 'Credenciales incorrectas.'
            })

        # Verificar si está bloqueado
        if usuario.esta_bloqueado():
            raise serializers.ValidationError({
                'detail': 'Cuenta bloqueada temporalmente por múltiples intentos fallidos. '
                          'Intenta nuevamente en unos minutos.'
            })

        # Verificar si está activo
        if not usuario.activo:
            raise serializers.ValidationError({
                'detail': 'Esta cuenta se encuentra desactivada. Contacta al administrador.'
            })

        # Validar contraseña
        if not usuario.check_password(password):
            usuario.registrar_intento_fallido()
            raise serializers.ValidationError({
                'detail': 'Credenciales incorrectas.'
            })

        if not cuenta_habilitada(usuario):
            raise serializers.ValidationError({'detail': 'Tu cuenta necesita un rol activo.'})

        # Login exitoso: resetear intentos
        usuario.resetear_intentos()
        self.user = usuario

        # Generar tokens
        refresh = self.get_token(usuario)

        data = {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'inicio': inicio_usuario(usuario),
            'usuario': {
                'id': usuario.id,
                'email': usuario.email,
                'nombre_completo': usuario.nombre_completo,
                'rol': usuario.rol.codigo if usuario.rol else None,
                'rol_nombre': usuario.rol.nombre if usuario.rol else None,
                'is_superuser': usuario.is_superuser,
            }
        }
        return data

