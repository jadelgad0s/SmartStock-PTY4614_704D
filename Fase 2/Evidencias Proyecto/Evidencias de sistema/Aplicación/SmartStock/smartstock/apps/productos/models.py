from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
import uuid
from apps.core.models import SoftDeleteModel, TimestampedModel

MAX_CANTIDAD_STOCK = 2_147_483_647

class Producto(SoftDeleteModel):
    sku = models.CharField(max_length=50, unique=True, validators=[RegexValidator(regex=r'^[A-Z0-9\-_]+$')])
    nombre = models.CharField(max_length=200, db_index=True)
    descripcion = models.TextField(blank=True)
    precio_referencia = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    imagen = models.ImageField(upload_to='productos/', blank=True, null=True)
    ficha_externa = models.ForeignKey(
        'FichaProductoExterna', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='productos_importados',
    )
    class Meta: db_table = 'productos'
    @property
    def codigo_principal(self):
        codigo = self.codigos_barra.filter(es_principal=True).first()
        return codigo.codigo if codigo else None


class FichaProductoExterna(models.Model):
    """Caché y procedencia de sugerencias públicas, separadas del inventario."""
    gtin = models.CharField(max_length=14, unique=True)
    datos = models.JSONField(default=dict)
    vence = models.DateTimeField(db_index=True)
    fecha_consulta = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fichas_producto_externas'


class CupoConsultaExterna(models.Model):
    """Ventana compartida por todos los usuarios y procesos del servidor."""
    proveedor = models.CharField(max_length=40, primary_key=True)
    intentos = models.JSONField(default=list)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'cupos_consulta_externa'


class CodigoBarra(TimestampedModel):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='codigos_barra')
    codigo = models.CharField(max_length=100, unique=True, db_index=True)
    tipo = models.CharField(max_length=10, choices=[('BARRA', 'Código de barras'), ('QR', 'Código QR')], default='BARRA')
    es_principal = models.BooleanField(default=False)
    class Meta: db_table = 'codigos_barra'
    def save(self, *args, **kwargs):
        if self.es_principal:
            CodigoBarra.objects.filter(producto=self.producto, es_principal=True).exclude(pk=self.pk).update(es_principal=False)
        super().save(*args, **kwargs)

# ==========================================
# BODEGAS Y UBICACIONES
# ==========================================
class Bodega(TimestampedModel):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200)
    activa = models.BooleanField(default=True)
    class Meta: db_table = 'bodegas'

class Pasillo(TimestampedModel):
    bodega = models.ForeignKey(Bodega, on_delete=models.CASCADE, related_name='pasillos')
    codigo = models.CharField(max_length=20)
    class Meta: db_table = 'pasillos'

class Estanteria(TimestampedModel):
    pasillo = models.ForeignKey(Pasillo, on_delete=models.CASCADE, related_name='estanterias')
    codigo = models.CharField(max_length=20)
    class Meta: db_table = 'estanterias'

class Nivel(TimestampedModel):
    estanteria = models.ForeignKey(Estanteria, on_delete=models.CASCADE, related_name='niveles')
    codigo = models.CharField(max_length=20)
    class Meta: db_table = 'niveles'

class Ubicacion(TimestampedModel):
    nivel = models.ForeignKey(Nivel, on_delete=models.CASCADE, related_name='ubicaciones')
    codigo = models.CharField(max_length=20)
    capacidad_maxima = models.IntegerField(default=0)
    class Meta: db_table = 'ubicaciones'

class ProductoUbicacion(TimestampedModel):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    ubicacion = models.ForeignKey(Ubicacion, on_delete=models.CASCADE)
    cantidad = models.IntegerField(default=0)
    class Meta: db_table = 'producto_ubicacion'

# ==========================================
# STOCK Y MOVIMIENTOS
# ==========================================
class StockBodega(TimestampedModel):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    bodega = models.ForeignKey(Bodega, on_delete=models.CASCADE)
    cantidad_total = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(MAX_CANTIDAD_STOCK)])
    class Meta:
        db_table = 'stock_bodega'
        constraints = [
            models.UniqueConstraint(fields=['producto', 'bodega'], name='stock_producto_bodega_unico'),
            models.CheckConstraint(condition=models.Q(cantidad_total__gte=0, cantidad_total__lte=MAX_CANTIDAD_STOCK), name='stock_cantidad_rango'),
        ]

class StockMinimo(TimestampedModel):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    bodega = models.ForeignKey(Bodega, on_delete=models.CASCADE)
    cantidad_minima = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(MAX_CANTIDAD_STOCK)])
    class Meta:
        db_table = 'stock_minimo'
        constraints = [
            models.UniqueConstraint(fields=['producto', 'bodega'], name='minimo_producto_bodega_unico'),
            models.CheckConstraint(condition=models.Q(cantidad_minima__gte=0, cantidad_minima__lte=MAX_CANTIDAD_STOCK), name='minimo_cantidad_rango'),
        ]

class TipoMovimiento(TimestampedModel):
    nombre = models.CharField(max_length=50) 
    operacion = models.CharField(max_length=1, choices=[('+', 'Suma'), ('-', 'Resta')])
    class Meta: db_table = 'tipo_movimiento'

class Movimiento(TimestampedModel):
    tipo = models.ForeignKey(TipoMovimiento, on_delete=models.PROTECT)
    bodega = models.ForeignKey(Bodega, on_delete=models.PROTECT)
    usuario = models.ForeignKey('usuarios.Usuario', on_delete=models.PROTECT)
    documento_referencia = models.CharField(max_length=100, blank=True)
    class Meta: db_table = 'movimientos'

class DetalleMovimiento(TimestampedModel):
    movimiento = models.ForeignKey(Movimiento, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(MAX_CANTIDAD_STOCK)])
    class Meta:
        db_table = 'detalle_movimiento'
        constraints = [models.CheckConstraint(condition=models.Q(cantidad__gte=1, cantidad__lte=MAX_CANTIDAD_STOCK), name='detalle_mov_cantidad_rango')]

class Transferencia(TimestampedModel):
    bodega_origen = models.ForeignKey(Bodega, related_name='transferencias_origen', on_delete=models.PROTECT)
    bodega_destino = models.ForeignKey(Bodega, related_name='transferencias_destino', on_delete=models.PROTECT)
    usuario = models.ForeignKey('usuarios.Usuario', on_delete=models.PROTECT)
    estado = models.CharField(max_length=20, choices=[('PENDIENTE', 'Pendiente'), ('COMPLETADA', 'Completada')])
    class Meta: db_table = 'transferencias'

class DetalleTransferencia(TimestampedModel):
    transferencia = models.ForeignKey(Transferencia, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(MAX_CANTIDAD_STOCK)])
    class Meta:
        db_table = 'detalle_transferencia'
        constraints = [models.CheckConstraint(condition=models.Q(cantidad__gte=1, cantidad__lte=MAX_CANTIDAD_STOCK), name='detalle_transfer_cantidad_rango')]

class MotivoMerma(TimestampedModel):
    descripcion = models.CharField(max_length=100)
    class Meta: db_table = 'motivo_merma'

class Merma(TimestampedModel):
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    bodega = models.ForeignKey(Bodega, on_delete=models.PROTECT)
    motivo = models.ForeignKey(MotivoMerma, on_delete=models.PROTECT)
    usuario = models.ForeignKey('usuarios.Usuario', on_delete=models.PROTECT)
    cantidad = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(MAX_CANTIDAD_STOCK)])
    observacion = models.TextField(blank=True, default='')
    class Meta:
        db_table = 'mermas'
        constraints = [models.CheckConstraint(condition=models.Q(cantidad__gte=1, cantidad__lte=MAX_CANTIDAD_STOCK), name='merma_cantidad_rango')]

class HistorialMovimientos(TimestampedModel):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    tipo_registro = models.CharField(max_length=50) 
    registro_id = models.IntegerField()
    descripcion = models.TextField()
    class Meta: db_table = 'historial_movimientos'

# ==========================================
# ALERTAS Y REPORTES
# ==========================================
class TipoAlerta(TimestampedModel):
    nombre = models.CharField(max_length=50)
    nivel_gravedad = models.IntegerField(default=1)
    class Meta: db_table = 'tipo_alerta'

class Alerta(TimestampedModel):
    tipo = models.ForeignKey(TipoAlerta, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    bodega = models.ForeignKey(Bodega, on_delete=models.CASCADE)
    mensaje = models.TextField()
    activa = models.BooleanField(default=True)
    class Meta: db_table = 'alertas'

class LogAlertas(TimestampedModel):
    alerta = models.ForeignKey(Alerta, on_delete=models.CASCADE)
    accion = models.CharField(max_length=100)
    usuario = models.ForeignKey('usuarios.Usuario', on_delete=models.SET_NULL, null=True)
    class Meta: db_table = 'log_alertas'

class TipoReporte(TimestampedModel):
    nombre = models.CharField(max_length=50)
    formato = models.CharField(max_length=10, choices=[('PDF', 'PDF'), ('CSV', 'CSV'), ('EXCEL', 'Excel')])
    class Meta: db_table = 'tipo_reporte'

class Reporte(TimestampedModel):
    tipo = models.ForeignKey(TipoReporte, on_delete=models.PROTECT)
    usuario = models.ForeignKey('usuarios.Usuario', on_delete=models.SET_NULL, null=True)
    archivo = models.FileField(upload_to='reportes/')
    parametros = models.JSONField(null=True, blank=True)
    class Meta: db_table = 'reportes'

# === NOTIFICACIONES INTERNAS ===
class Notificacion(TimestampedModel):
    """Avisos de cambios para quien realiza la operación y administración."""
    TIPO_CHOICES = [
        ('MOVIMIENTO', 'Movimiento de stock'),
        ('MERMA', 'Merma registrada'),
        ('STOCK_BAJO', 'Stock bajo'),
        ('OTRO', 'Otro'),
    ]
    usuario_destino = models.ForeignKey(
        'usuarios.Usuario', on_delete=models.CASCADE, related_name='notificaciones'
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='OTRO')
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField()
    link = models.CharField(max_length=200, blank=True)
    leida = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = 'notificaciones'
        ordering = ['-fecha_creacion']


class EstadoStockSMS(TimestampedModel):
    """Un ciclo por producto/bodega: bajo y agotado se avisan una sola vez."""
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    bodega = models.ForeignKey(Bodega, on_delete=models.CASCADE)
    ciclo = models.UUIDField(default=uuid.uuid4)
    nivel_maximo = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'estado_stock_sms'
        constraints = [models.UniqueConstraint(fields=['producto', 'bodega'], name='sms_estado_producto_bodega')]


class EnvioAlertaSMS(TimestampedModel):
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'), ('ENVIANDO', 'Envío en curso'),
        ('ACEPTADO', 'Aceptado por Twilio'), ('ENVIADO', 'Enviado a la red'),
        ('ENTREGADO', 'Entregado'), ('NO_ENTREGADO', 'No entregado'),
        ('RECHAZADO', 'Rechazado'), ('INCIERTO', 'Resultado por confirmar'),
        ('CANCELADO', 'Cancelado'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True)
    bodega = models.ForeignKey(Bodega, on_delete=models.SET_NULL, null=True)
    ciclo = models.UUIDField()
    nivel = models.PositiveSmallIntegerField()
    sku = models.CharField(max_length=50)
    producto_nombre = models.CharField(max_length=200)
    bodega_nombre = models.CharField(max_length=100)
    cantidad = models.IntegerField()
    minimo = models.IntegerField()
    destinatario = models.CharField(max_length=16)
    mensaje = models.CharField(max_length=160)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE', db_index=True)
    intentos = models.PositiveSmallIntegerField(default=0)
    ultimo_intento = models.DateTimeField(null=True, blank=True)
    proximo_intento = models.DateTimeField(null=True, blank=True)
    twilio_sid = models.CharField(max_length=34, unique=True, null=True, blank=True)
    codigo_error = models.CharField(max_length=12, blank=True)
    detalle = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'envios_alertas_sms'
        verbose_name = 'envío de alerta SMS'
        verbose_name_plural = 'envíos de alertas SMS'
        ordering = ['-fecha_creacion', '-id']
        constraints = [models.UniqueConstraint(fields=['ciclo', 'nivel', 'destinatario'], name='sms_un_envio_por_nivel_ciclo')]


class LimiteDiarioSMS(models.Model):
    """El bloqueo de esta fila coordina el presupuesto entre procesos web."""
    fecha = models.DateField(unique=True)
    intentos = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'limite_diario_sms'

