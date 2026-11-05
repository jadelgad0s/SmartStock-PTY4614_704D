from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from apps.core.models import TimestampedModel, SoftDeleteModel

class Permiso(TimestampedModel):
    codigo = models.CharField(max_length=100, unique=True, validators=[RegexValidator(regex=r'^[a-z_]+$')])
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    modulo = models.CharField(max_length=50, db_index=True)
    class Meta: db_table = 'permisos'

class Rol(SoftDeleteModel):
    nombre = models.CharField(max_length=50, unique=True)
    codigo = models.CharField(max_length=50, unique=True, validators=[RegexValidator(regex=r'^[a-z_]+$')])
    descripcion = models.TextField(blank=True)
    permisos = models.ManyToManyField(Permiso, through='RolPermiso', related_name='roles', blank=True)
    es_sistema = models.BooleanField(default=False)
    class Meta: db_table = 'roles'
    def tiene_permiso(self, codigo_permiso): return self.permisos.filter(codigo=codigo_permiso).exists()

class RolPermiso(TimestampedModel):
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name='rol_permisos')
    permiso = models.ForeignKey(Permiso, on_delete=models.CASCADE, related_name='permiso_roles')
    class Meta:
        db_table = 'rol_permiso'
        unique_together = ('rol', 'permiso')

class UsuarioManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email: raise ValueError('El email es obligatorio')
        email = self.normalize_email(email)
        usuario = self.model(email=email, **extra_fields)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('activo', True)
        return self.create_user(email, password, **extra_fields)

class Usuario(AbstractBaseUser, PermissionsMixin, SoftDeleteModel):
    email = models.EmailField(unique=True)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name='usuarios', null=True, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    ultimo_login = models.DateTimeField(null=True, blank=True)
    intentos_fallidos = models.PositiveIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    is_staff = models.BooleanField(default=False)
    objects = UsuarioManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nombres', 'apellidos']
    class Meta: db_table = 'usuarios'

    @property
    def nombre_completo(self): return f'{self.nombres} {self.apellidos}'.strip()
    @property
    def cuenta_protegida(self):
        return self.is_superuser or bool(self.rol_id and self.rol.codigo == 'administrador')
    def tiene_permiso(self, codigo_permiso):
        if not self.activo: return False
        if self.is_superuser: return True
        if not self.rol_id or not self.rol.activo: return False
        return self.rol.tiene_permiso(codigo_permiso)
    def esta_bloqueado(self):
        from django.utils import timezone
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > timezone.now())
    def registrar_intento_fallido(self, max_intentos=5, minutos_bloqueo=15):
        from django.utils import timezone
        from datetime import timedelta
        self.intentos_fallidos += 1
        if self.intentos_fallidos >= max_intentos:
            self.bloqueado_hasta = timezone.now() + timedelta(minutes=minutos_bloqueo)
        self.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])
    def resetear_intentos(self):
        from django.utils import timezone
        self.intentos_fallidos = 0
        self.bloqueado_hasta = None
        self.ultimo_login = timezone.now()
        self.save(update_fields=['intentos_fallidos', 'bloqueado_hasta', 'ultimo_login'])

class Sesion(TimestampedModel):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='sesiones')
    token_jti = models.CharField(max_length=255, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    activa = models.BooleanField(default=True)
    fecha_expiracion = models.DateTimeField()
    class Meta: db_table = 'sesiones'

