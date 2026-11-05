from django.db import models

class TimestampedModel(models.Model):
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    class Meta: abstract = True

class SoftDeleteModel(TimestampedModel):
    activo = models.BooleanField(default=True)
    class Meta: abstract = True
    def desactivar(self):
        self.activo = False
        self.save(update_fields=['activo', 'fecha_modificacion'])
    def activar(self):
        self.activo = True
        self.save(update_fields=['activo', 'fecha_modificacion'])

class Auditoria(TimestampedModel):
    ACCION_CHOICES = [
        ('CREATE', 'Creación'), ('UPDATE', 'Modificación'),
        ('DEACTIVATE', 'Desactivación'), ('REACTIVATE', 'Reactivación'),
        ('DELETE', 'Eliminación definitiva'), ('LOGIN', 'Inicio de sesión'),
        ('LOGOUT', 'Cierre de sesión'), ('LOGIN_FAILED', 'Intento fallido de login'),
    ]
    usuario = models.ForeignKey('usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='acciones_auditoria')
    accion = models.CharField(max_length=20, choices=ACCION_CHOICES)
    modelo = models.CharField(max_length=100)
    objeto_id = models.CharField(max_length=50, blank=True)
    descripcion = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    class Meta:
        db_table = 'auditoria'

