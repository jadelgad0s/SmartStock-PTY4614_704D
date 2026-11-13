"""Selección de bodegas y bloqueos compartidos con las operaciones de stock."""
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import Bodega, StockBodega


def bodegas_activas():
    return Bodega.objects.filter(activa=True)


def datos_bodega(bodega):
    return {
        'id': bodega.pk, 'nombre': bodega.nombre, 'activa': bodega.activa,
        'etiqueta': bodega.nombre,
    }


def opciones_bodegas(incluir_inactivas=False):
    qs = Bodega.objects.all() if incluir_inactivas else bodegas_activas()
    return [datos_bodega(b) for b in qs.order_by('nombre', 'id')]


class ConsultaBodegaSerializer(serializers.Serializer):
    bodega = serializers.IntegerField(required=False, min_value=1)


def bodega_consulta(parametros):
    serializer = ConsultaBodegaSerializer(data=parametros)
    serializer.is_valid(raise_exception=True)
    return obtener_bodega(serializer.validated_data.get('bodega'))


def obtener_bodega(identificador=None, *, bloquear=False, crear_central=False):
    """Los clientes antiguos sin bodega conservan su selección de Central.

    Orden de bloqueo: producto (en el llamador), bodega y stock.
    """
    if identificador is None:
        bodega = bodegas_activas().filter(nombre='Bodega Central').order_by('id').first()
        if bodega is None and crear_central and not Bodega.objects.filter(nombre='Bodega Central').exists():
            bodega, _ = Bodega.objects.get_or_create(nombre='Bodega Central', defaults={'direccion': 'Casa Matriz'})
        if bodega is None:
            return None
    else:
        bodega = Bodega.objects.filter(pk=identificador).first()
        if bodega is None:
            raise ValidationError({'bodega_id': 'Selecciona una bodega activa.'})
    if bloquear:
        bodega = Bodega.objects.select_for_update().get(pk=bodega.pk)
    if not bodega.activa:
        raise ValidationError({'bodega_id': 'Selecciona una bodega activa.'})
    return bodega


def stock_para_operar(producto, bodega):
    """Una operación considera todo el stock heredado de esta pareja."""
    filas = list(StockBodega.objects.select_for_update().filter(producto=producto, bodega=bodega).order_by('id'))
    return (filas[0] if filas else None), sum(f.cantidad_total for f in filas), [f.pk for f in filas[1:]]
