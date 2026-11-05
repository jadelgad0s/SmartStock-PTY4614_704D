from django.contrib import admin
from .models import Auditoria


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = ('fecha_creacion', 'usuario', 'accion', 'modelo', 'objeto_id', 'ip_address')
    list_filter = ('accion', 'modelo', 'fecha_creacion')
    search_fields = ('usuario__email', 'modelo', 'objeto_id', 'descripcion')
    readonly_fields = ('fecha_creacion', 'fecha_modificacion', 'usuario', 'accion',
                       'modelo', 'objeto_id', 'descripcion', 'ip_address', 'user_agent')
    date_hierarchy = 'fecha_creacion'
    ordering = ('-fecha_creacion',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
