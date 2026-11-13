"""Registro de stock e historial paginado del módulo de Movimientos."""
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from apps.core.responses import error_response, success_response
from apps.core.utils import registrar_auditoria
from apps.usuarios.navegacion import es_administrador
from apps.usuarios.permissions import TienePermiso
from .models import DetalleMovimiento, Movimiento, Producto, StockBodega, TipoMovimiento
from .views_notificaciones import notificar_administradores
from .alertas_sms import evaluar_alerta_sms
from .bodegas import bodega_consulta, obtener_bodega, stock_para_operar
from .consulta_codigos import productos_registrados

MAX_CANTIDAD = 2_147_483_647


class MovimientoPagination(PageNumberPagination):
    page_size = 25


class PuedeVerMovimientos(TienePermiso):
    permiso_requerido = 'ver_movimiento'

    def has_permission(self, request, view):
        return es_administrador(request.user) or super().has_permission(request, view)


class FiltrosMovimientoSerializer(serializers.Serializer):
    bodega = serializers.IntegerField(required=False, min_value=1)
    search = serializers.CharField(max_length=200, required=False, allow_blank=True)
    tipo = serializers.ChoiceField(choices=('ENTRADA', 'SALIDA', ''), required=False)
    desde = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])
    hasta = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])

    def validate(self, attrs):
        if attrs.get('desde') and attrs.get('hasta') and attrs['desde'] > attrs['hasta']:
            raise serializers.ValidationError('La fecha inicial no puede ser posterior a la final.')
        return attrs


class CrearMovimientoSerializer(serializers.Serializer):
    bodega_id = serializers.IntegerField(required=False, min_value=1)
    producto_id = serializers.IntegerField(min_value=1)
    tipo_movimiento = serializers.ChoiceField(choices=('ENTRADA', 'SALIDA'))
    cantidad = serializers.IntegerField(min_value=1, max_value=MAX_CANTIDAD)
    observacion = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')


def consulta_movimientos():
    return DetalleMovimiento.objects.select_related(
        'movimiento__usuario', 'movimiento__tipo', 'movimiento__bodega', 'producto',
    ).order_by('-movimiento__fecha_creacion', '-id')


def datos_movimiento(detalle):
    movimiento = detalle.movimiento
    fecha = timezone.localtime(movimiento.fecha_creacion)
    return {
        'id': detalle.pk,
        'movimiento_id': movimiento.pk,
        'fecha': fecha.strftime('%d/%m/%Y %H:%M'),
        'fecha_iso': fecha.isoformat(),
        'tipo': 'ENTRADA' if movimiento.tipo.operacion == '+' else 'SALIDA',
        'tipo_nombre': movimiento.tipo.nombre,
        'producto_id': detalle.producto_id,
        'producto': detalle.producto.nombre,
        'sku': detalle.producto.sku,
        'cantidad': detalle.cantidad,
        'usuario': movimiento.usuario.nombre_completo,
        'bodega': movimiento.bodega.nombre,
        'bodega_id': movimiento.bodega_id,
        'documento_referencia': movimiento.documento_referencia,
    }


def cuenta_inactiva(request):
    if not request.user.activo:
        return error_response('La cuenta está desactivada.', status_code=status.HTTP_403_FORBIDDEN)
    return None


@api_view(['GET'])
@permission_classes([IsAuthenticated, PuedeVerMovimientos])
def historial_movimientos(request):
    rechazo = cuenta_inactiva(request)
    if rechazo is not None:
        return rechazo
    filtros = FiltrosMovimientoSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    datos = filtros.validated_data
    qs = consulta_movimientos()
    if datos.get('bodega'):
        qs = qs.filter(movimiento__bodega_id=datos['bodega'])
    if datos.get('search'):
        qs = qs.filter(Q(producto__nombre__icontains=datos['search']) | Q(producto__sku__icontains=datos['search']))
    if datos.get('tipo'):
        qs = qs.filter(movimiento__tipo__operacion='+' if datos['tipo'] == 'ENTRADA' else '-')
    # La transformación date usa la zona horaria configurada en Django (Chile).
    if datos.get('desde'):
        qs = qs.filter(movimiento__fecha_creacion__date__gte=datos['desde'])
    if datos.get('hasta'):
        qs = qs.filter(movimiento__fecha_creacion__date__lte=datos['hasta'])
    paginador = MovimientoPagination()
    pagina = paginador.paginate_queryset(qs, request)
    return paginador.get_paginated_response([datos_movimiento(item) for item in pagina])


@api_view(['GET'])
@permission_classes([IsAuthenticated, PuedeVerMovimientos])
def detalle_movimiento(request, pk):
    rechazo = cuenta_inactiva(request)
    if rechazo is not None:
        return rechazo
    detalle = consulta_movimientos().filter(pk=pk).first()
    if detalle is None:
        return error_response('El movimiento no existe.', status_code=status.HTTP_404_NOT_FOUND)
    return success_response(data=datos_movimiento(detalle))


@api_view(['GET'])
@permission_classes([IsAuthenticated, PuedeVerMovimientos])
def resolver_producto_movimiento(request):
    """Resolución exacta, sin depender de la primera página del catálogo.

    El stock corresponde a la bodega seleccionada para registrar la operación.
    """
    rechazo = cuenta_inactiva(request)
    if rechazo is not None:
        return rechazo
    codigo = request.query_params.get('codigo', '').strip()
    if not codigo or len(codigo) > 100:
        return error_response('Ingresa un SKU o código de barras de hasta 100 caracteres.')
    coincidencias = productos_registrados(codigo)
    if len(coincidencias) > 1:
        return error_response('El código coincide con más de un producto. Revisa sus identificadores.', status_code=409)
    producto = coincidencias[0] if coincidencias and coincidencias[0].activo else None
    if producto is None:
        return error_response('No se encontró un producto activo con ese código.', status_code=status.HTTP_404_NOT_FOUND)
    bodega = bodega_consulta(request.query_params)
    disponible = (StockBodega.objects.filter(producto=producto, bodega=bodega).aggregate(n=Sum('cantidad_total'))['n'] or 0) if bodega else 0
    return success_response(data={
        'id': producto.pk, 'sku': producto.sku, 'nombre': producto.nombre,
        'stock_disponible': disponible,
        'bodega': bodega.nombre if bodega else 'Bodega Central',
        'bodega_id': bodega.pk if bodega else None,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def registrar_movimiento(request):
    rechazo = cuenta_inactiva(request)
    if rechazo is not None:
        return rechazo
    serializer = CrearMovimientoSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response('Revisa los datos del movimiento.', errores=serializer.errors)
    info = serializer.validated_data
    entrada = info['tipo_movimiento'] == 'ENTRADA'
    permiso = 'registrar_entrada' if entrada else 'registrar_salida'
    if not request.user.tiene_permiso(permiso):
        return error_response('No tienes permiso para registrar este tipo de movimiento.', status_code=status.HTTP_403_FORBIDDEN)

    with transaction.atomic():
        # Serializar operaciones del mismo producto, incluso si aún no tiene
        # fila de stock. Mermas también bloquea la fila de StockBodega.
        producto = Producto.objects.select_for_update(no_key=True).filter(pk=info['producto_id'], activo=True).first()
        if producto is None:
            return error_response('El producto no existe o está inactivo.', status_code=status.HTTP_404_NOT_FOUND)
        bodega = obtener_bodega(info.get('bodega_id'), bloquear=True, crear_central=entrada and 'bodega_id' not in info)
        if bodega is None:
            return error_response('No hay una Bodega Central activa disponible. Selecciona una bodega.')
        stock, anterior, duplicados = stock_para_operar(producto, bodega)
        cantidad = info['cantidad']
        if not entrada and anterior < cantidad:
            return error_response(
                f'Stock insuficiente en {bodega.nombre}. Disponible: {anterior} unidades.',
                errores={'stock_disponible': anterior}, status_code=status.HTTP_409_CONFLICT,
            )
        nuevo = anterior + cantidad if entrada else anterior - cantidad
        if nuevo > MAX_CANTIDAD or nuevo < 0:
            return error_response('La cantidad supera el límite de stock permitido.')
        if stock is None:
            stock = StockBodega.objects.create(producto=producto, bodega=bodega, cantidad_total=0)
        filtro_stock = StockBodega.objects.filter(pk=stock.pk, cantidad_total=stock.cantidad_total)
        actualizados = filtro_stock.update(
            cantidad_total=nuevo,
            fecha_modificacion=timezone.now(),
        )
        if actualizados != 1:
            return error_response('El stock cambió durante el registro. Inténtalo nuevamente.', status_code=status.HTTP_409_CONFLICT)
        if duplicados:
            StockBodega.objects.filter(pk__in=duplicados).delete()

        tipo = TipoMovimiento.objects.filter(nombre=info['tipo_movimiento'], operacion='+' if entrada else '-').order_by('id').first()
        if tipo is None:
            tipo = TipoMovimiento.objects.create(nombre=info['tipo_movimiento'], operacion='+' if entrada else '-')
        movimiento = Movimiento.objects.create(
            tipo=tipo, bodega=bodega, usuario=request.user, documento_referencia=info['observacion'],
        )
        detalle = DetalleMovimiento.objects.create(movimiento=movimiento, producto=producto, cantidad=cantidad)
        registrar_auditoria(
            accion='CREATE', modelo='Movimiento', objeto_id=movimiento.pk,
            descripcion=f'{info["tipo_movimiento"]} de {cantidad} unid. SKU: {producto.sku}. Bodega: {bodega.nombre}.',
            usuario_override=request.user,
        )
        notificar_administradores(
            tipo='MOVIMIENTO', titulo='Entrada registrada' if entrada else 'Salida registrada',
            mensaje=f'{cantidad} unidades de «{producto.nombre}» ({producto.sku}). '
                    f'Stock en {bodega.nombre}: {nuevo} unidades.',
            link='/movimientos/', actor_id=request.user.id,
        )
        resultado = datos_movimiento(detalle)
        resultado.update(stock_anterior=anterior, stock_restante=nuevo)
        evaluar_alerta_sms(producto, bodega)
    return success_response(
        data=resultado, mensaje='Movimiento registrado y stock actualizado.', status_code=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated, PuedeVerMovimientos])
def ultimos_movimientos(request):
    """Compatibilidad para clientes anteriores; el nuevo historial no tiene este límite."""
    rechazo = cuenta_inactiva(request)
    if rechazo is not None:
        return rechazo
    return success_response(data=[datos_movimiento(item) for item in consulta_movimientos()[:15]])
