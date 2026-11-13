"""API para registrar y consultar mermas de inventario por bodega."""
from django.db import transaction
from django.db.models import Q, OuterRef, Subquery, IntegerField, Value, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination

from apps.core.responses import error_response, success_response
from apps.core.utils import registrar_auditoria
from .models import Merma, MotivoMerma, Producto, StockBodega
from .alertas_sms import evaluar_alerta_sms
from .bodegas import bodega_consulta, obtener_bodega, stock_para_operar


MOTIVOS_MERMA = {
    'DAÑO': 'Daño en Bodega',
    'VENCIDO': 'Producto Vencido',
    'EXTRAVIO': 'Pérdida/Extravío',
    'DEFECTO': 'Falla de Fábrica',
}


class CrearMermaSerializer(serializers.Serializer):
    bodega_id = serializers.IntegerField(required=False, min_value=1)
    producto_id = serializers.IntegerField(min_value=1)
    cantidad = serializers.IntegerField(min_value=1, max_value=2_147_483_647)
    motivo = serializers.ChoiceField(choices=tuple((codigo, codigo) for codigo in MOTIVOS_MERMA))
    observacion = serializers.CharField(max_length=1000, required=True, allow_blank=False, trim_whitespace=True)


def datos_merma(merma):
    return {
        'id': merma.id,
        'producto_id': merma.producto_id,
        'fecha_iso': timezone.localtime(merma.fecha_creacion).isoformat(),
        'fecha': timezone.localtime(merma.fecha_creacion).strftime('%d/%m/%Y %H:%M'),
        'producto': merma.producto.nombre,
        'sku': merma.producto.sku,
        'cantidad': merma.cantidad,
        'motivo': merma.motivo.descripcion,
        'motivo_codigo': next((codigo for codigo, texto in MOTIVOS_MERMA.items() if texto == merma.motivo.descripcion), ''),
        'observacion': merma.observacion,
        'responsable': merma.usuario.nombre_completo,
        'estado': 'Registrada',
        'bodega': merma.bodega.nombre,
        'bodega_id': merma.bodega_id,
    }


class MermaPagination(PageNumberPagination):
    page_size = 25


class FiltrosMermaSerializer(serializers.Serializer):
    bodega = serializers.IntegerField(required=False, min_value=1)
    search = serializers.CharField(max_length=200, required=False, allow_blank=True)
    motivo = serializers.ChoiceField(choices=tuple(MOTIVOS_MERMA) + ('',), required=False)
    desde = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])
    hasta = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])

    def validate(self, attrs):
        if attrs.get('desde') and attrs.get('hasta') and attrs['desde'] > attrs['hasta']:
            raise serializers.ValidationError('La fecha inicial no puede ser posterior a la final.')
        return attrs


def verificar_acceso_mermas(request):
    if not request.user.activo:
        return error_response('La cuenta está desactivada.', status_code=status.HTTP_403_FORBIDDEN)
    if not request.user.tiene_permiso('registrar_merma'):
        return error_response('No tienes permiso para consultar o registrar mermas.', status_code=status.HTTP_403_FORBIDDEN)
    return None


def consultar_mermas():
    return Merma.objects.select_related('producto', 'motivo', 'bodega', 'usuario').order_by('-fecha_creacion', '-id')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def historial_mermas(request):
    rechazo = verificar_acceso_mermas(request)
    if rechazo is not None:
        return rechazo
    filtros = FiltrosMermaSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    info = filtros.validated_data
    qs = consultar_mermas()
    if info.get('bodega'):
        qs = qs.filter(bodega_id=info['bodega'])
    if info.get('search'):
        qs = qs.filter(Q(producto__nombre__icontains=info['search']) | Q(producto__sku__icontains=info['search']))
    if info.get('motivo'):
        qs = qs.filter(motivo__descripcion=MOTIVOS_MERMA[info['motivo']])
    # Django interpreta date en la zona horaria de Chile configurada en el proyecto.
    if info.get('desde'):
        qs = qs.filter(fecha_creacion__date__gte=info['desde'])
    if info.get('hasta'):
        qs = qs.filter(fecha_creacion__date__lte=info['hasta'])
    paginador = MermaPagination()
    pagina = paginador.paginate_queryset(qs, request)
    return paginador.get_paginated_response([datos_merma(item) for item in pagina])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detalle_merma(request, pk):
    rechazo = verificar_acceso_mermas(request)
    if rechazo is not None:
        return rechazo
    merma = consultar_mermas().filter(pk=pk).first()
    if merma is None:
        return error_response('La merma no existe.', status_code=status.HTTP_404_NOT_FOUND)
    return success_response(data=datos_merma(merma))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def productos_merma(request):
    """Catálogo activo paginado con el stock de la bodega que se descontará."""
    rechazo = verificar_acceso_mermas(request)
    if rechazo is not None:
        return rechazo
    consulta = serializers.CharField(max_length=200, allow_blank=True).run_validation(request.query_params.get('search', ''))
    bodega = bodega_consulta(request.query_params)
    qs = Producto.objects.filter(activo=True).order_by('nombre', 'id')
    if consulta:
        qs = qs.filter(Q(sku__icontains=consulta) | Q(nombre__icontains=consulta) | Q(codigos_barra__codigo__icontains=consulta)).distinct()
    stock = StockBodega.objects.filter(producto_id=OuterRef('pk'), bodega=bodega).order_by().values('producto_id').annotate(total=Sum('cantidad_total')).values('total')
    qs = qs.annotate(stock_disponible=Coalesce(Subquery(stock, output_field=IntegerField()), Value(0)))
    paginador = MermaPagination()
    pagina = paginador.paginate_queryset(qs, request)
    return paginador.get_paginated_response([{
        'id': item.pk, 'nombre': item.nombre, 'sku': item.sku,
        'stock_disponible': item.stock_disponible, 'bodega': bodega.nombre if bodega else 'Bodega Central',
        'bodega_id': bodega.pk if bodega else None,
    } for item in pagina])


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def mermas_api(request):
    """Lista las 50 mermas recientes o registra una baja real de stock.

    La bodega se selecciona expresamente. Los clientes anteriores sin selección
    conservan Bodega Central. La autorización se valida en backend.
    """
    if not request.user.activo:
        return error_response('La cuenta está desactivada.', status_code=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        if not request.user.tiene_permiso('registrar_merma'):
            return error_response('No tienes permiso para consultar mermas.', status_code=status.HTTP_403_FORBIDDEN)
        queryset = consultar_mermas()[:50]
        return success_response(data=[datos_merma(item) for item in queryset])

    if not request.user.tiene_permiso('registrar_merma'):
        return error_response('No tienes permiso para registrar mermas.', status_code=status.HTTP_403_FORBIDDEN)

    serializer = CrearMermaSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            mensaje='Revisa los datos de la merma.',
            errores=serializer.errors,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    info = serializer.validated_data
    # Una sola transacción: descuento, registro y auditoría deben tener éxito juntos.
    with transaction.atomic():
        # Mismo orden de bloqueo que Movimientos; no_key permite conservar
        # referencias al producto mientras se serializan sus cambios de stock.
        producto = Producto.objects.select_for_update(no_key=True).filter(pk=info['producto_id'], activo=True).first()
        if producto is None:
            return error_response('El producto no existe o está inactivo.', status_code=status.HTTP_404_NOT_FOUND)
        bodega = obtener_bodega(info.get('bodega_id'), bloquear=True)
        if bodega is None:
            return error_response(
                'Todavía no existe la Bodega Central con stock disponible.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        stock, disponible, duplicados = stock_para_operar(producto, bodega)
        if stock is None or disponible < info['cantidad']:
            return error_response(
                f'Stock insuficiente en {bodega.nombre}. Disponible: {disponible} unidades.',
                errores={'stock_disponible': disponible},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Un UPDATE condicionado protege también frente a solicitudes simultáneas.
        actualizados = (StockBodega.objects
                       .filter(pk=stock.pk, cantidad_total=stock.cantidad_total)
                       .update(cantidad_total=disponible - info['cantidad'], fecha_modificacion=timezone.now()))
        if actualizados != 1:
            return error_response(
                'El stock cambió durante el registro. Inténtalo nuevamente.',
                status_code=status.HTTP_409_CONFLICT,
            )
        if duplicados:
            StockBodega.objects.filter(pk__in=duplicados).delete()

        descripcion = MOTIVOS_MERMA[info['motivo']]
        motivo = MotivoMerma.objects.filter(descripcion=descripcion).order_by('id').first()
        if motivo is None:
            motivo = MotivoMerma.objects.create(descripcion=descripcion)

        merma = Merma.objects.create(
            producto=producto,
            bodega=bodega,
            motivo=motivo,
            usuario=request.user,
            cantidad=info['cantidad'],
            observacion=info['observacion'],
        )
        registrar_auditoria(
            accion='CREATE',
            modelo='Merma',
            objeto_id=merma.id,
            descripcion=f'Merma de {info["cantidad"]} unid. SKU: {producto.sku} - {descripcion}. Bodega: {bodega.nombre}.',
            usuario_override=request.user,
        )
        from .views_notificaciones import notificar_administradores
        notificar_administradores(
            tipo='MERMA',
            titulo=f'Merma #{merma.pk} registrada',
            mensaje=f'Se dieron de baja {info["cantidad"]} unidades de «{producto.nombre}» ({producto.sku}). '
                    f'Stock restante en {bodega.nombre}: {disponible - info["cantidad"]} unidades.',
            link='/mermas/',
            actor_id=request.user.id,
        )
        resultado = datos_merma(merma)
        resultado['stock_anterior'] = disponible
        resultado['stock_restante'] = disponible - info['cantidad']
        evaluar_alerta_sms(producto, bodega)

    return success_response(
        data=resultado,
        mensaje='Merma registrada y stock descontado correctamente.',
        status_code=status.HTTP_201_CREATED,
    )

