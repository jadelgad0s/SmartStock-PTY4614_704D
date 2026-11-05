"""Cálculo compartido del stock y sus mínimos, sin multiplicar filas relacionadas."""
from django.db.models import F, IntegerField, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce

from .models import Bodega, StockBodega, StockMinimo
from .bodegas import bodegas_activas, datos_bodega

AGOTADO = Q(stock_calculado__lte=0)
BAJO = Q(stock_calculado__gt=0, minimo_calculado__gt=0, stock_calculado__lte=F('minimo_calculado'))


def anotar_stock(queryset, bodega_id=None):
    stock = StockBodega.objects.filter(producto_id=OuterRef('pk'))
    minimo = StockMinimo.objects.filter(producto_id=OuterRef('pk'))
    if bodega_id is not None:
        stock = stock.filter(bodega_id=bodega_id)
        minimo = minimo.filter(bodega_id=bodega_id)
    else:
        # Las consultas antiguas sin bodega conservan el total físico global.
        # Ese total no se clasifica contra mínimos de bodegas distintas.
        minimo = minimo.none()
    stock = stock.order_by().values('producto_id').annotate(total=Sum('cantidad_total')).values('total')
    minimo = minimo.order_by().values('producto_id').annotate(total=Max('cantidad_minima')).values('total')
    return queryset.annotate(
        stock_calculado=Coalesce(Subquery(stock, output_field=IntegerField()), 0),
        minimo_calculado=Coalesce(Subquery(minimo, output_field=IntegerField()), 0),
    )


def estado_stock(cantidad, minimo):
    if cantidad <= 0:
        return 'agotado'
    return 'bajo' if minimo > 0 and cantidad <= minimo else 'suficiente'


def existencias_producto(producto_id):
    cantidades = dict(StockBodega.objects.filter(producto_id=producto_id).values('bodega_id').annotate(total=Sum('cantidad_total')).values_list('bodega_id', 'total'))
    minimos = dict(StockMinimo.objects.filter(producto_id=producto_id).values('bodega_id').annotate(total=Max('cantidad_minima')).values_list('bodega_id', 'total'))
    datos = []
    for bodega in bodegas_activas().order_by('nombre', 'id'):
        cantidad = cantidades.get(bodega.pk, 0)
        minimo = max(0, minimos.get(bodega.pk, 0))
        datos.append({**datos_bodega(bodega), 'stock': cantidad, 'minimo': minimo, 'estado': estado_stock(cantidad, minimo)})
    return datos
