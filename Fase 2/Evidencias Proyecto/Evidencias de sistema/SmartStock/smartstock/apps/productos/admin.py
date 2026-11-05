from django.contrib import admin
from .models import Producto, CodigoBarra, EnvioAlertaSMS
from .alertas_sms import telefono_oculto


class CodigoBarraInline(admin.TabularInline):
    model = CodigoBarra
    extra = 1


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('sku', 'nombre', 'precio_referencia', 'activo', 'fecha_creacion')
    list_filter = ('activo',)
    search_fields = ('sku', 'nombre', 'descripcion')
    inlines = [CodigoBarraInline]
    ordering = ('nombre',)


@admin.register(CodigoBarra)
class CodigoBarraAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'producto', 'tipo', 'es_principal')
    list_filter = ('tipo', 'es_principal')
    search_fields = ('codigo', 'producto__sku', 'producto__nombre')


@admin.register(EnvioAlertaSMS)
class EnvioAlertaSMSAdmin(admin.ModelAdmin):
    list_display = ('sku', 'bodega_nombre', 'telefono', 'estado', 'intentos', 'fecha_creacion')
    list_filter = ('estado', 'nivel')
    search_fields = ('sku', 'producto_nombre', 'twilio_sid')
    fields = ('id', 'sku', 'producto_nombre', 'bodega_nombre', 'cantidad', 'minimo', 'telefono',
              'mensaje', 'estado', 'intentos', 'ultimo_intento', 'twilio_sid', 'codigo_error',
              'detalle', 'fecha_creacion', 'fecha_modificacion')
    readonly_fields = fields

    @admin.display(description='Destinatario')
    def telefono(self, obj):
        return telefono_oculto(obj.destinatario)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

