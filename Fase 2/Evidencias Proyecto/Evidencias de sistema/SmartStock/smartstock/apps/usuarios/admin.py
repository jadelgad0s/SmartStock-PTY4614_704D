from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Usuario, Rol, Permiso, RolPermiso, Sesion


@admin.register(Permiso)
class PermisoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'modulo')
    list_filter = ('modulo',)
    search_fields = ('codigo', 'nombre')
    ordering = ('modulo', 'codigo')


class RolPermisoInline(admin.TabularInline):
    model = RolPermiso
    extra = 1


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'es_sistema', 'activo', 'fecha_creacion')
    list_filter = ('es_sistema', 'activo')
    search_fields = ('nombre', 'codigo')
    inlines = [RolPermisoInline]
    ordering = ('nombre',)


@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    list_display = ('email', 'nombre_completo', 'rol', 'activo', 'ultimo_login')
    list_filter = ('activo', 'rol', 'is_staff', 'is_superuser')
    search_fields = ('email', 'nombres', 'apellidos')
    ordering = ('apellidos', 'nombres')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Información personal', {'fields': ('nombres', 'apellidos', 'telefono')}),
        ('Rol y permisos', {'fields': ('rol', 'activo', 'is_staff', 'is_superuser')}),
        ('Seguridad', {'fields': ('intentos_fallidos', 'bloqueado_hasta', 'ultimo_login'),
                       'classes': ('collapse',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nombres', 'apellidos', 'rol', 'password1', 'password2'),
        }),
    )

    readonly_fields = ('ultimo_login', 'intentos_fallidos', 'bloqueado_hasta')
    filter_horizontal = ()


@admin.register(Sesion)
class SesionAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'ip_address', 'fecha_creacion', 'fecha_expiracion', 'activa')
    list_filter = ('activa', 'fecha_creacion')
    search_fields = ('usuario__email', 'ip_address')
    readonly_fields = ('usuario', 'token_jti', 'ip_address', 'user_agent',
                       'fecha_creacion', 'fecha_expiracion')

    def has_add_permission(self, request):
        return False
