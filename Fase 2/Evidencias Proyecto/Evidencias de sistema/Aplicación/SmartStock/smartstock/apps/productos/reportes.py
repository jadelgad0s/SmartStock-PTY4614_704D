"""Consultas de inventario de solo lectura; el Kardex incluye las bajas por merma."""
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import connection, transaction
from django.db.models import Case, CharField, Count, F, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Concat
from django.utils import timezone
from rest_framework import serializers

from .models import Bodega, DetalleMovimiento, Merma, Producto, StockBodega
from .stock import AGOTADO, BAJO, anotar_stock, estado_stock

ZONA = ZoneInfo('America/Santiago')
TITULOS = {
    'existencias': 'Existencias actuales', 'critico': 'Stock crítico actual',
    'movimientos': 'Movimientos de inventario', 'mermas': 'Mermas y bajas',
    'kardex': 'Kardex por producto',
}
NOTA_KARDEX = ('El saldo inicial se calcula desde las existencias actuales y los registros disponibles. '
               'Puede incluir stock cargado antes del historial; no certifica un conteo físico histórico.')


@contextmanager
def lectura_consistente():
    """Materializa resultados antes de cerrar la instantánea, también al exportar.

    No mantiene un cursor ni una transacción durante la descarga. Las pruebas
    TestCase ya están dentro de una transacción y no cambian su aislamiento.
    """
    exterior = not connection.in_atomic_block
    with transaction.atomic():
        if exterior and connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        yield


class FiltrosReporte(serializers.Serializer):
    informe = serializers.ChoiceField(choices=tuple(TITULOS), default='existencias')
    bodega = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)
    producto = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)
    search = serializers.CharField(max_length=200, required=False, allow_blank=True)
    desde = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])
    hasta = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])
    tipo = serializers.ChoiceField(choices=('', 'ENTRADA', 'SALIDA'), default='')
    productos = serializers.ChoiceField(choices=('activos', 'todos', 'inactivos'), default='activos')

    def validate(self, datos):
        informe = datos['informe']
        if informe in ('existencias', 'critico', 'kardex') and not datos.get('bodega'):
            raise serializers.ValidationError({'bodega': 'Selecciona una bodega para este reporte.'})
        if informe == 'kardex' and not datos.get('producto'):
            raise serializers.ValidationError({'producto': 'Selecciona un producto para consultar su Kardex.'})
        if informe in ('existencias', 'critico') and (datos.get('desde') or datos.get('hasta')):
            raise serializers.ValidationError('Las existencias y el stock crítico muestran el estado actual, sin filtro de fechas.')
        if informe != 'movimientos' and datos['tipo']:
            raise serializers.ValidationError({'tipo': 'El tipo de movimiento solo se aplica al reporte de movimientos.'})
        if informe == 'kardex' and datos.get('search'):
            raise serializers.ValidationError({'search': 'Selecciona el producto del Kardex; no se filtran sus asientos por texto.'})
        if datos.get('desde') and datos.get('hasta') and datos['desde'] > datos['hasta']:
            raise serializers.ValidationError('La fecha inicial no puede ser posterior a la final.')
        if datos.get('hasta') and datos['hasta'].year == 9999:
            raise serializers.ValidationError({'hasta': 'La fecha debe ser anterior al año 9999.'})
        return datos


def filtrar_fechas(qs, datos, campo):
    if datos.get('desde'):
        qs = qs.filter(**{campo + '__gte': datetime.combine(datos['desde'], time.min, tzinfo=ZONA)})
    if datos.get('hasta'):
        qs = qs.filter(**{campo + '__lt': datetime.combine(datos['hasta'] + timedelta(days=1), time.min, tzinfo=ZONA)})
    return qs


def busqueda_producto(qs, texto, prefijo=''):
    if not texto:
        return qs
    return qs.filter(Q(**{prefijo + 'nombre__icontains': texto}) | Q(**{prefijo + 'sku__icontains': texto}))


def totales(movimientos, mermas):
    m = movimientos.aggregate(
        entradas=Sum('cantidad', filter=Q(movimiento__tipo__operacion='+')),
        salidas=Sum('cantidad', filter=Q(movimiento__tipo__operacion='-')),
    )
    bajas = mermas.aggregate(n=Sum('cantidad'))['n'] or 0
    return (m['entradas'] or 0), (m['salidas'] or 0), bajas


def asientos_movimientos(qs):
    return qs.order_by().annotate(
        r_fecha=F('movimiento__fecha_creacion'), r_id=F('pk'),
        r_prioridad=Value(0, output_field=IntegerField()), r_registro=F('movimiento_id'),
        r_tipo=Case(
            When(movimiento__tipo__nombre='TRANSFERENCIA_ENTRADA', then=Value('Transferencia: entrada')),
            When(movimiento__tipo__nombre='TRANSFERENCIA_SALIDA', then=Value('Transferencia: salida')),
            When(movimiento__tipo__operacion='+', then=Value('Entrada')),
            default=Value('Salida'), output_field=CharField(),
        ),
        r_producto=F('producto__nombre'), r_sku=F('producto__sku'), r_bodega=F('movimiento__bodega__nombre'),
        r_nombre=F('movimiento__usuario__nombres'), r_apellido=F('movimiento__usuario__apellidos'),
        r_referencia=F('movimiento__documento_referencia'),
        r_entrada=Case(When(movimiento__tipo__operacion='+', then=F('cantidad')), default=Value(0), output_field=IntegerField()),
        r_salida=Case(When(movimiento__tipo__operacion='-', then=F('cantidad')), default=Value(0), output_field=IntegerField()),
    ).values(*CAMPOS_ASIENTO)


def asientos_mermas(qs):
    return qs.order_by().annotate(
        r_fecha=F('fecha_creacion'), r_id=F('pk'), r_prioridad=Value(1, output_field=IntegerField()),
        r_registro=F('pk'), r_tipo=Value('Merma', output_field=CharField()),
        r_producto=F('producto__nombre'), r_sku=F('producto__sku'), r_bodega=F('bodega__nombre'),
        r_nombre=F('usuario__nombres'), r_apellido=F('usuario__apellidos'),
        r_referencia=Concat('motivo__descripcion', Value(' · '), 'observacion', output_field=CharField()),
        r_entrada=Value(0, output_field=IntegerField()), r_salida=F('cantidad'),
    ).values(*CAMPOS_ASIENTO)


CAMPOS_ASIENTO = ('r_fecha', 'r_id', 'r_prioridad', 'r_registro', 'r_tipo', 'r_producto', 'r_sku',
                  'r_bodega', 'r_nombre', 'r_apellido', 'r_referencia', 'r_entrada', 'r_salida')


def columnas(*campos):
    etiquetas = {
        'fecha': 'Fecha / hora', 'registro': 'Registro', 'tipo': 'Tipo', 'producto': 'Producto',
        'sku': 'SKU', 'bodega': 'Bodega', 'responsable': 'Responsable', 'referencia': 'Referencia / observación',
        'entrada': 'Entradas', 'salida': 'Salidas', 'saldo': 'Saldo', 'stock': 'Unidades',
        'minimo': 'Mínimo', 'estado': 'Estado del stock', 'activo': 'Producto activo',
        'motivo': 'Motivo', 'cantidad': 'Unidades dadas de baja',
    }
    return [{'campo': c, 'etiqueta': etiquetas[c],
             'numero': c in ('entrada', 'salida', 'saldo', 'stock', 'minimo', 'cantidad')} for c in campos]


class PlanReporte:
    def __init__(self, parametros):
        filtros = FiltrosReporte(data=parametros)
        filtros.is_valid(raise_exception=True)
        self.datos = filtros.validated_data
        self.informe = self.datos['informe']
        self.ahora = timezone.now()
        self.bodega = self.producto = None
        if self.datos.get('bodega'):
            self.bodega = Bodega.objects.filter(pk=self.datos['bodega']).first()
            if self.bodega is None:
                raise serializers.ValidationError({'bodega': 'La bodega seleccionada no existe.'})
        if self.datos.get('producto'):
            self.producto = Producto.objects.filter(pk=self.datos['producto']).first()
            if self.producto is None:
                raise serializers.ValidationError({'producto': 'El producto seleccionado no existe.'})
        self.resumen, self.notas = [], []
        if self.informe in ('existencias', 'critico'):
            self.preparar_stock()
        else:
            self.preparar_actividad()

    def preparar_stock(self):
        qs = Producto.objects.all()
        if self.datos['productos'] != 'todos':
            qs = qs.filter(activo=self.datos['productos'] == 'activos')
        qs = busqueda_producto(qs, self.datos.get('search'))
        if self.producto:
            qs = qs.filter(pk=self.producto.pk)
        qs = anotar_stock(qs, self.bodega.pk)
        if self.informe == 'critico':
            qs = qs.filter(AGOTADO | BAJO)
        self.qs = qs.order_by('nombre', 'id')
        r = qs.aggregate(unidades=Sum('stock_calculado'), productos=Count('pk'),
                         agotados=Count('pk', filter=AGOTADO), bajos=Count('pk', filter=BAJO))
        self.resumen = [('Productos', r['productos']), ('Unidades', r['unidades'] or 0),
                        ('Agotados', r['agotados']), ('Con stock bajo', r['bajos'])]
        self.columnas = columnas('sku', 'producto', 'bodega', 'stock', 'minimo', 'estado', 'activo')
        self.notas = ['Estado actual al generar el reporte. Sin registro de stock se consideran 0 unidades. '
                      'Un mínimo de 0 desactiva el aviso de stock bajo, pero el producto puede estar agotado.']

    def preparar_actividad(self):
        # La instantánea de lectura, no el reloj de Python, delimita los registros
        # disponibles. Así no se omite un asiento cuyo stock ya está en la instantánea.
        movimientos = DetalleMovimiento.objects.all()
        mermas = Merma.objects.all()
        if self.bodega:
            movimientos = movimientos.filter(movimiento__bodega=self.bodega)
            mermas = mermas.filter(bodega=self.bodega)
        if self.producto:
            movimientos = movimientos.filter(producto=self.producto)
            mermas = mermas.filter(producto=self.producto)
        movimientos = busqueda_producto(movimientos, self.datos.get('search'), 'producto__')
        mermas = busqueda_producto(mermas, self.datos.get('search'), 'producto__')
        if self.informe == 'kardex':
            stock = StockBodega.objects.filter(producto=self.producto, bodega=self.bodega).aggregate(n=Sum('cantidad_total'))['n'] or 0
            posteriores = {k: v for k, v in self.datos.items() if k == 'desde'}
            e, s, b = totales(filtrar_fechas(movimientos, posteriores, 'movimiento__fecha_creacion'),
                              filtrar_fechas(mermas, posteriores, 'fecha_creacion'))
            self.inicial = stock - e + s + b
        self.movimientos = filtrar_fechas(movimientos, self.datos, 'movimiento__fecha_creacion')
        self.mermas = filtrar_fechas(mermas, self.datos, 'fecha_creacion')
        if self.datos['tipo']:
            self.movimientos = self.movimientos.filter(movimiento__tipo__operacion='+' if self.datos['tipo'] == 'ENTRADA' else '-')
        if self.informe == 'mermas':
            self.qs = self.mermas.select_related('producto', 'bodega', 'usuario', 'motivo').order_by('-fecha_creacion', '-id')
            self.columnas = columnas('fecha', 'registro', 'sku', 'producto', 'bodega', 'cantidad', 'motivo', 'referencia', 'responsable')
            self.resumen = [('Registros', self.qs.count()), ('Unidades dadas de baja', self.qs.aggregate(n=Sum('cantidad'))['n'] or 0)]
        elif self.informe == 'movimientos':
            self.qs = asientos_movimientos(self.movimientos).order_by('-r_fecha', '-r_id')
            e, s, _ = totales(self.movimientos, Merma.objects.none())
            self.columnas = columnas('fecha', 'registro', 'tipo', 'sku', 'producto', 'bodega', 'entrada', 'salida', 'referencia', 'responsable')
            self.resumen = [('Entradas', e), ('Salidas', s), ('Variación por movimientos', e - s)]
            self.notas = ['Incluye las entradas y salidas de transferencias. Las bajas por merma se consultan en Mermas y bajas y en el Kardex.']
        else:
            self.qs = asientos_movimientos(self.movimientos).union(asientos_mermas(self.mermas), all=True).order_by('r_fecha', 'r_prioridad', 'r_id')
            e, s, b = totales(self.movimientos, self.mermas)
            self.columnas = columnas('fecha', 'registro', 'tipo', 'entrada', 'salida', 'saldo', 'referencia', 'responsable')
            self.resumen = [('Saldo inicial calculado', self.inicial), ('Entradas', e),
                            ('Salidas (incluye mermas)', s + b), ('Saldo final calculado', self.inicial + e - s - b)]
            self.notas = [NOTA_KARDEX, 'Orden cronológico. Las transferencias usan sus movimientos de entrada o salida y se contabilizan una sola vez.']

    def saldo_antes(self, primera):
        """Saldo anterior a la página sin volver a recorrer ni cargar las anteriores."""
        fecha, pk, fuente = primera['r_fecha'], primera['r_id'], primera['r_prioridad']
        mov = Q(movimiento__fecha_creacion__lt=fecha)
        merma = Q(fecha_creacion__lt=fecha)
        mov |= Q(movimiento__fecha_creacion=fecha) if fuente else Q(movimiento__fecha_creacion=fecha, pk__lt=pk)
        if fuente:
            merma |= Q(fecha_creacion=fecha, pk__lt=pk)
        e, s, b = totales(self.movimientos.filter(mov), self.mermas.filter(merma))
        return self.inicial + e - s - b

    def filas(self, elementos, *, pagina=False):
        saldo = self.inicial if self.informe == 'kardex' else 0
        for indice, item in enumerate(elementos):
            if self.informe in ('existencias', 'critico'):
                estado = estado_stock(item.stock_calculado, max(0, item.minimo_calculado))
                yield {'id': item.pk, 'sku': item.sku, 'producto': item.nombre, 'bodega': self.bodega.nombre,
                       'stock': item.stock_calculado, 'minimo': max(0, item.minimo_calculado),
                       'estado': {'agotado': 'Agotado', 'bajo': 'Stock bajo', 'suficiente': 'Stock suficiente'}[estado],
                       'activo': 'Sí' if item.activo else 'No'}
            elif self.informe == 'mermas':
                yield {'id': item.pk, 'fecha': timezone.localtime(item.fecha_creacion, ZONA).strftime('%d/%m/%Y %H:%M:%S'),
                       'registro': f'Merma #{item.pk}', 'sku': item.producto.sku, 'producto': item.producto.nombre,
                       'bodega': item.bodega.nombre, 'cantidad': item.cantidad, 'motivo': item.motivo.descripcion,
                       'referencia': item.observacion, 'responsable': item.usuario.nombre_completo}
            else:
                if self.informe == 'kardex':
                    if pagina and indice == 0:
                        saldo = self.saldo_antes(item)
                    saldo += item['r_entrada'] - item['r_salida']
                yield {'id': f'{item["r_prioridad"]}-{item["r_id"]}',
                       'fecha': timezone.localtime(item['r_fecha'], ZONA).strftime('%d/%m/%Y %H:%M:%S'),
                       'registro': ('Merma' if item['r_prioridad'] else 'Movimiento') + f' #{item["r_registro"]}',
                       'tipo': item['r_tipo'], 'sku': item['r_sku'], 'producto': item['r_producto'],
                       'bodega': item['r_bodega'], 'entrada': item['r_entrada'], 'salida': item['r_salida'],
                       'saldo': saldo, 'referencia': item['r_referencia'],
                       'responsable': f'{item["r_nombre"]} {item["r_apellido"]}'.strip()}

    def iterar(self):
        offset = 0
        while True:
            lote = list(self.qs[offset:offset + 1000])
            if not lote:
                break
            yield from lote
            offset += len(lote)

    def metadatos(self):
        filtros = [('Bodega', self.bodega.nombre + (' (inactiva)' if not self.bodega.activa else '') if self.bodega else 'Todas las bodegas')]
        if self.producto:
            filtros.append(('Producto', f'{self.producto.sku} · {self.producto.nombre}'))
        if self.datos.get('search'):
            filtros.append(('Búsqueda', self.datos['search']))
        if self.informe in ('existencias', 'critico'):
            filtros.append(('Productos', {'activos': 'Activos', 'todos': 'Todos', 'inactivos': 'Inactivos'}[self.datos['productos']]))
        else:
            filtros.extend((campo.capitalize(), self.datos[campo].strftime('%d/%m/%Y') if self.datos.get(campo) else 'Sin límite') for campo in ('desde', 'hasta'))
        if self.datos['tipo']:
            filtros.append(('Tipo', self.datos['tipo'].capitalize()))
        return {'informe': self.informe, 'titulo': TITULOS[self.informe], 'columnas': self.columnas,
                'resumen': [{'etiqueta': e, 'valor': v} for e, v in self.resumen], 'notas': self.notas,
                'filtros': filtros, 'generado': timezone.localtime(self.ahora, ZONA).isoformat(),
                'zona_horaria': str(ZONA), 'orden': 'Cronológico' if self.informe == 'kardex' else
                'Producto A–Z' if self.informe in ('existencias', 'critico') else 'Más recientes primero'}
