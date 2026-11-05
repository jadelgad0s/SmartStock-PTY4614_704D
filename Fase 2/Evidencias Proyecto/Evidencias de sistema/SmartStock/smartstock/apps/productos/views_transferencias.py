"""Transferencias inmediatas usando las tablas de inventario existentes."""
import json

from django.db import transaction
from django.db.models import IntegerField, OuterRef, Prefetch, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from apps.core.responses import error_response, success_response
from apps.core.utils import registrar_auditoria
from apps.usuarios.models import Usuario
from apps.usuarios.navegacion import puede_transferir
from .alertas_sms import evaluar_alerta_sms
from .bodegas import opciones_bodegas, stock_para_operar
from .consulta_codigos import productos_registrados
from .models import (
    Bodega, DetalleMovimiento, DetalleTransferencia, HistorialMovimientos,
    Movimiento, Producto, StockBodega, TipoMovimiento, Transferencia,
)
from .views_bodegas import permisos_bodegas
from .views_notificaciones import notificar_administradores

MAX_CANTIDAD = 2_147_483_647
TIPO_HISTORIAL = 'TRANSFERENCIA'


class TransferenciasPagination(PageNumberPagination):
    page_size = 25


class FiltrosTransferenciaSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)
    origen = serializers.IntegerField(required=False, min_value=1)
    destino = serializers.IntegerField(required=False, min_value=1)
    estado = serializers.ChoiceField(required=False, choices=('COMPLETADA', 'PENDIENTE', ''))
    desde = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])
    hasta = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])

    def validate(self, attrs):
        if attrs.get('desde') and attrs.get('hasta') and attrs['desde'] > attrs['hasta']:
            raise serializers.ValidationError('La fecha inicial no puede ser posterior a la final.')
        return attrs


class BodegasTransferenciaSerializer(serializers.Serializer):
    origen = serializers.IntegerField(min_value=1)
    destino = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        if attrs['origen'] == attrs['destino']:
            raise serializers.ValidationError('Selecciona bodegas distintas para origen y destino.')
        return attrs


class CrearTransferenciaSerializer(serializers.Serializer):
    bodega_origen_id = serializers.IntegerField(min_value=1)
    bodega_destino_id = serializers.IntegerField(min_value=1)
    producto_id = serializers.IntegerField(min_value=1)
    cantidad = serializers.IntegerField(min_value=1, max_value=MAX_CANTIDAD)
    solicitud_id = serializers.UUIDField()

    def validate(self, attrs):
        if attrs['bodega_origen_id'] == attrs['bodega_destino_id']:
            raise serializers.ValidationError('La bodega de origen y la de destino deben ser distintas.')
        desconocidos = set(self.initial_data) - set(self.fields)
        if desconocidos:
            raise serializers.ValidationError({c: 'Este campo no está permitido.' for c in desconocidos})
        return attrs


def acceso_transferencias(request):
    if not request.user.activo:
        return error_response('La cuenta está desactivada.', status_code=status.HTTP_403_FORBIDDEN)
    if not puede_transferir(request.user):
        return error_response('No tienes permiso para consultar o registrar transferencias.', status_code=403)
    return None


def consulta_transferencias():
    detalles = DetalleTransferencia.objects.select_related('producto').order_by('id')
    return Transferencia.objects.select_related('bodega_origen', 'bodega_destino', 'usuario').prefetch_related(
        Prefetch('detalles', queryset=detalles),
    ).order_by('-fecha_creacion', '-id')


def leer_historial(transferencia_id):
    registro = HistorialMovimientos.objects.filter(tipo_registro=TIPO_HISTORIAL, registro_id=transferencia_id).order_by('-id').first()
    if registro:
        try:
            datos = json.loads(registro.descripcion)
            if isinstance(datos, dict) and datos.get('version') == 1:
                return datos
        except (ValueError, TypeError):
            pass
    return {}


def datos_transferencia(transferencia, historial=None):
    fecha = timezone.localtime(transferencia.fecha_creacion)
    detalles = [{'id': d.pk, 'producto_id': d.producto_id, 'producto': d.producto.nombre,
                 'sku': d.producto.sku, 'cantidad': d.cantidad} for d in transferencia.detalles.all()]
    registro = historial or {}
    return {
        'id': transferencia.pk, 'fecha': fecha.strftime('%d/%m/%Y %H:%M'), 'fecha_iso': fecha.isoformat(),
        'estado': transferencia.estado, 'usuario': transferencia.usuario.nombre_completo,
        'usuario_id': transferencia.usuario_id,
        'bodega_origen': {'id': transferencia.bodega_origen_id, 'nombre': transferencia.bodega_origen.nombre},
        'bodega_destino': {'id': transferencia.bodega_destino_id, 'nombre': transferencia.bodega_destino.nombre},
        'detalles': detalles, 'cantidad_total': sum(d['cantidad'] for d in detalles),
        'stock': registro.get('stock'), 'movimientos': registro.get('movimientos'),
    }


def seleccionar_bodegas(parametros):
    serializer = BodegasTransferenciaSerializer(data=parametros)
    serializer.is_valid(raise_exception=True)
    datos = serializer.validated_data
    bodegas = {b.pk: b for b in Bodega.objects.filter(pk__in=(datos['origen'], datos['destino']), activa=True)}
    if len(bodegas) != 2:
        raise serializers.ValidationError('Selecciona bodegas de origen y destino activas.')
    return bodegas[datos['origen']], bodegas[datos['destino']]


def productos_con_stock(origen, destino):
    def total(bodega):
        return StockBodega.objects.filter(producto_id=OuterRef('pk'), bodega=bodega).order_by().values('producto_id').annotate(n=Sum('cantidad_total')).values('n')
    return Producto.objects.filter(activo=True).annotate(
        stock_origen=Coalesce(Subquery(total(origen), output_field=IntegerField()), Value(0)),
        stock_destino=Coalesce(Subquery(total(destino), output_field=IntegerField()), Value(0)),
    ).order_by('nombre', 'id')


def datos_producto(producto, origen, destino):
    return {'id': producto.pk, 'sku': producto.sku, 'nombre': producto.nombre,
            'bodega_origen_id': origen.pk, 'bodega_destino_id': destino.pk,
            'stock_origen': producto.stock_origen, 'stock_destino': producto.stock_destino}


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def opciones_transferencias(request):
    rechazo = acceso_transferencias(request)
    if rechazo is not None:
        return rechazo
    activas = opciones_bodegas()
    return success_response(data={
        'bodegas': activas, 'bodegas_historial': opciones_bodegas(incluir_inactivas=True),
        'bodega_predeterminada': next((b['id'] for b in activas if b['nombre'] == 'Bodega Central'), activas[0]['id'] if activas else None),
        'permisos': {**permisos_bodegas(request.user), 'registrar': request.user.tiene_permiso('registrar_transferencia')},
    })


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def productos_transferencias(request):
    rechazo = acceso_transferencias(request)
    if rechazo is not None:
        return rechazo
    origen, destino = seleccionar_bodegas(request.query_params)
    texto = serializers.CharField(max_length=200, allow_blank=True).run_validation(request.query_params.get('search', ''))
    qs = productos_con_stock(origen, destino).filter(stock_origen__gt=0)
    if texto:
        qs = qs.filter(Q(nombre__icontains=texto) | Q(sku__icontains=texto) | Q(codigos_barra__codigo__icontains=texto)).distinct()
    paginador = TransferenciasPagination()
    pagina = paginador.paginate_queryset(qs, request)
    return paginador.get_paginated_response([datos_producto(p, origen, destino) for p in pagina])


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def resolver_transferencia(request):
    rechazo = acceso_transferencias(request)
    if rechazo is not None:
        return rechazo
    origen, destino = seleccionar_bodegas(request.query_params)
    codigo = serializers.CharField(max_length=100, allow_blank=False).run_validation(request.query_params.get('codigo', ''))
    coincidencias = productos_registrados(codigo)
    if len(coincidencias) > 1:
        return error_response('El código coincide con más de un producto. Revisa sus identificadores.', status_code=409)
    if not coincidencias or not coincidencias[0].activo:
        return error_response('No se encontró un producto activo con ese código.', status_code=404)
    producto = productos_con_stock(origen, destino).get(pk=coincidencias[0].pk)
    return success_response(data=datos_producto(producto, origen, destino))


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detalle_transferencia(request, pk):
    rechazo = acceso_transferencias(request)
    if rechazo is not None:
        return rechazo
    transferencia = consulta_transferencias().filter(pk=pk).first()
    if transferencia is None:
        return error_response('La transferencia no existe.', status_code=404)
    return success_response(data=datos_transferencia(transferencia, leer_historial(pk)))


class ConflictoTransferencia(Exception):
    def __init__(self, mensaje, errores=None):
        super().__init__(mensaje)
        self.errores = errores


def solicitud_anterior(usuario, info):
    # El usuario está bloqueado antes de consultar la clave: dos confirmaciones
    # simultáneas del mismo usuario se serializan, incluso con productos distintos.
    prefijo = '{"solicitud_id":"' + str(info['solicitud_id']) + '",'
    ids = HistorialMovimientos.objects.filter(tipo_registro=TIPO_HISTORIAL, descripcion__startswith=prefijo).values('registro_id')
    transferencia = consulta_transferencias().filter(usuario=usuario, pk__in=Subquery(ids)).first()
    if transferencia is None:
        return None
    detalles = list(transferencia.detalles.all())
    coincide = (transferencia.estado == 'COMPLETADA' and len(detalles) == 1
                and transferencia.bodega_origen_id == info['bodega_origen_id']
                and transferencia.bodega_destino_id == info['bodega_destino_id']
                and detalles[0].producto_id == info['producto_id'] and detalles[0].cantidad == info['cantidad'])
    if not coincide:
        raise ConflictoTransferencia('La solicitud ya fue utilizada con otros datos. Revisa el historial.',
                                    {'codigo': 'SOLICITUD_UTILIZADA', 'transferencia_id': transferencia.pk})
    return transferencia


def registrar_asiento(transferencia, producto, bodega, cantidad, entrada, contraparte):
    nombre = 'TRANSFERENCIA_ENTRADA' if entrada else 'TRANSFERENCIA_SALIDA'
    operacion = '+' if entrada else '-'
    tipo = TipoMovimiento.objects.filter(nombre=nombre, operacion=operacion).order_by('id').first()
    if tipo is None:
        tipo = TipoMovimiento.objects.create(nombre=nombre, operacion=operacion)
    referencia = f'Transferencia #{transferencia.pk}: {"desde" if entrada else "hacia"} {contraparte.nombre}'
    mov = Movimiento.objects.create(tipo=tipo, bodega=bodega, usuario=transferencia.usuario, documento_referencia=referencia[:100])
    DetalleMovimiento.objects.create(movimiento=mov, producto=producto, cantidad=cantidad)
    return mov.pk


def guardar_transferencia(request, info):
    with transaction.atomic():
        # no_key permite las referencias FK de otros movimientos/notificaciones.
        usuario = Usuario.objects.select_for_update(no_key=True).filter(pk=request.user.pk).first()
        if usuario is None or not puede_transferir(usuario):
            return error_response('No tienes permiso para registrar transferencias.', status_code=403)
        anterior = solicitud_anterior(usuario, info)
        if anterior:
            return success_response(data=datos_transferencia(anterior, leer_historial(anterior.pk)),
                                    mensaje='La transferencia ya estaba registrada.')
        producto = Producto.objects.select_for_update(no_key=True).filter(pk=info['producto_id'], activo=True).first()
        if producto is None:
            return error_response('El producto no existe o está inactivo.', status_code=404)
        ids = (info['bodega_origen_id'], info['bodega_destino_id'])
        bodegas = {b.pk: b for b in Bodega.objects.select_for_update().filter(pk__in=ids).order_by('id')}
        if len(bodegas) != 2 or any(not b.activa for b in bodegas.values()):
            return error_response('Selecciona bodegas de origen y destino activas.')
        origen, destino = (bodegas[id_bodega] for id_bodega in ids)
        filas = {id_bodega: stock_para_operar(producto, bodegas[id_bodega]) for id_bodega in sorted(ids)}
        stock_origen, disponible, _ = filas[origen.pk]
        stock_destino, recibido, _ = filas[destino.pk]
        cantidades = {'stock_origen': disponible, 'stock_destino': recibido}
        if disponible < info['cantidad']:
            raise ConflictoTransferencia(f'Stock insuficiente en {origen.nombre}. Disponible: {disponible} unidades.', cantidades)
        if recibido < 0:
            raise ConflictoTransferencia('Revisa el stock de destino: contiene una cantidad negativa.', cantidades)
        nuevos = {origen.pk: disponible - info['cantidad'], destino.pk: recibido + info['cantidad']}
        if any(n < 0 or n > MAX_CANTIDAD for n in nuevos.values()):
            raise ConflictoTransferencia('La cantidad supera el límite de stock permitido.', cantidades)
        for id_bodega in sorted(ids):
            stock, _, duplicados = filas[id_bodega]
            if stock is None:
                StockBodega.objects.create(producto=producto, bodega=bodegas[id_bodega], cantidad_total=nuevos[id_bodega])
            else:
                n = StockBodega.objects.filter(pk=stock.pk, cantidad_total=stock.cantidad_total).update(
                    cantidad_total=nuevos[id_bodega], fecha_modificacion=timezone.now())
                if n != 1:
                    raise ConflictoTransferencia('El stock cambió durante el registro. Vuelve a consultar las cantidades.')
                if duplicados:
                    StockBodega.objects.filter(pk__in=duplicados).delete()
        transferencia = Transferencia.objects.create(bodega_origen=origen, bodega_destino=destino, usuario=usuario, estado='COMPLETADA')
        DetalleTransferencia.objects.create(transferencia=transferencia, producto=producto, cantidad=info['cantidad'])
        movimientos = {
            'salida': registrar_asiento(transferencia, producto, origen, info['cantidad'], False, destino),
            'entrada': registrar_asiento(transferencia, producto, destino, info['cantidad'], True, origen),
        }
        historial = {'solicitud_id': str(info['solicitud_id']), 'version': 1,
                     'stock': {'origen_anterior': disponible, 'origen_posterior': nuevos[origen.pk],
                               'destino_anterior': recibido, 'destino_posterior': nuevos[destino.pk]},
                     'movimientos': movimientos}
        # Instantánea e identificador de confirmación en el historial ya existente.
        HistorialMovimientos.objects.create(producto=producto, tipo_registro=TIPO_HISTORIAL,
            registro_id=transferencia.pk, descripcion=json.dumps(historial, separators=(',', ':')))
        texto = f'Transferencia #{transferencia.pk}: {info["cantidad"]} unidades de «{producto.nombre}» ({producto.sku}). {origen.nombre} → {destino.nombre}.'
        registrar_auditoria(accion='CREATE', modelo='Transferencia', objeto_id=transferencia.pk,
                           descripcion=texto, usuario_override=usuario)
        notificar_administradores(tipo='MOVIMIENTO', titulo=f'Transferencia #{transferencia.pk} completada',
                                 mensaje=texto, link='/transferencias/', actor_id=usuario.pk)
        # La salida puede generar una alerta; la entrada puede cerrar el ciclo
        # de stock bajo o cancelar un SMS pendiente de la bodega de destino.
        evaluar_alerta_sms(producto, origen)
        evaluar_alerta_sms(producto, destino)
        return success_response(data=datos_transferencia(transferencia, historial),
                                mensaje='Transferencia completada.', status_code=status.HTTP_201_CREATED)


@never_cache
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def transferencias_api(request):
    rechazo = acceso_transferencias(request)
    if rechazo is not None:
        return rechazo
    if request.method == 'POST':
        serializer = CrearTransferenciaSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Revisa los datos de la transferencia.', errores=serializer.errors)
        try:
            return guardar_transferencia(request, serializer.validated_data)
        except ConflictoTransferencia as error:
            return error_response(str(error), errores=error.errores, status_code=409)
    serializer = FiltrosTransferenciaSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    datos = serializer.validated_data
    qs = consulta_transferencias()
    if datos.get('search'):
        qs = qs.filter(Q(detalles__producto__nombre__icontains=datos['search']) | Q(detalles__producto__sku__icontains=datos['search'])).distinct()
    if datos.get('origen'):
        qs = qs.filter(bodega_origen_id=datos['origen'])
    if datos.get('destino'):
        qs = qs.filter(bodega_destino_id=datos['destino'])
    if datos.get('estado'):
        qs = qs.filter(estado=datos['estado'])
    if datos.get('desde'):
        qs = qs.filter(fecha_creacion__date__gte=datos['desde'])
    if datos.get('hasta'):
        qs = qs.filter(fecha_creacion__date__lte=datos['hasta'])
    paginador = TransferenciasPagination()
    pagina = paginador.paginate_queryset(qs, request)
    return paginador.get_paginated_response([datos_transferencia(t) for t in pagina])
