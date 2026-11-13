"""
Views del módulo de productos.
"""
from urllib.parse import urlencode
from rest_framework import viewsets, status, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Max, Q
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator

from apps.core.responses import success_response, error_response
from apps.core.utils import registrar_auditoria
from apps.usuarios.navegacion import es_administrador, puede_acceder_admin
from apps.usuarios.permissions import PermisoLectura
from apps.usuarios.permissions import EsAdministrador
from apps.core.safe_delete import tiene_relaciones
from django.db import IntegrityError, transaction
from .models import Bodega, Producto, CodigoBarra, StockMinimo
from .stock import AGOTADO, BAJO, anotar_stock, estado_stock
from .bodegas import bodegas_activas, obtener_bodega, opciones_bodegas
from .alertas_sms import cancelar_alertas_producto, evaluar_alerta_sms
from .views_notificaciones import notificar_administradores
from .serializers import (
    ProductoListSerializer,
    ProductoDetailSerializer,
    ProductoCreateUpdateSerializer,
    CodigoBarraSerializer,
)


class ProductoPagination(PageNumberPagination):
    """25 productos por página, sin alterar la paginación de otros módulos."""
    page_size = 25


class FiltrosCatalogoSerializer(serializers.Serializer):
    bodega = serializers.IntegerField(required=False, min_value=1)
    disponibilidad = serializers.ChoiceField(choices=('', 'suficiente', 'bajo', 'agotado'), required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)

    def validate(self, attrs):
        if attrs.get('disponibilidad') and not attrs.get('bodega'):
            raise serializers.ValidationError({'bodega': 'Selecciona una bodega para filtrar la disponibilidad.'})
        return attrs


class ConsultaStockMinimoSerializer(serializers.Serializer):
    bodega = serializers.IntegerField(min_value=1)


class GuardarStockMinimoSerializer(ConsultaStockMinimoSerializer):
    cantidad_minima = serializers.IntegerField(min_value=0, max_value=2147483647)


@method_decorator(never_cache, name='dispatch')
class ProductoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de productos.

    Endpoints:
        GET    /api/v1/productos/                Lista de productos
        POST   /api/v1/productos/                Crear producto
        GET    /api/v1/productos/{id}/           Detalle
        PUT    /api/v1/productos/{id}/           Actualizar
        PATCH  /api/v1/productos/{id}/           Actualizar parcial
        DELETE /api/v1/productos/{id}/           Desactivar
        POST   /api/v1/productos/{id}/activar/   Reactivar
        GET/PATCH /api/v1/productos/{id}/stock-minimo/ Mínimo por bodega
        GET    /api/v1/productos/buscar/?q=...   Búsqueda por SKU, nombre o código
    """
    queryset = Producto.objects.prefetch_related('codigos_barra').all()
    permission_classes = [IsAuthenticated, PermisoLectura]
    permiso_lectura = 'ver_producto'
    pagination_class = ProductoPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['activo']
    search_fields = ['sku', 'nombre', 'descripcion', 'codigos_barra__codigo']
    ordering_fields = ['nombre', 'sku', 'precio_referencia', 'fecha_creacion', 'id']
    ordering = ['nombre', 'id']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ('list', 'buscar'):
            filtros = FiltrosCatalogoSerializer(data=self.request.query_params)
            filtros.is_valid(raise_exception=True)
            datos = filtros.validated_data
            self.bodega_catalogo = None
            if datos.get('bodega'):
                self.bodega_catalogo = bodegas_activas().filter(pk=datos['bodega']).values('id', 'nombre').first()
                if self.bodega_catalogo is None:
                    raise serializers.ValidationError({'bodega': 'Selecciona una bodega activa.'})
            qs = anotar_stock(qs, datos.get('bodega'))
            if datos.get('disponibilidad'):
                criterios = {'agotado': AGOTADO, 'bajo': BAJO, 'suficiente': ~(AGOTADO | BAJO)}
                qs = qs.filter(criterios[datos['disponibilidad']])
        elif self.action in ('update', 'partial_update', 'destroy', 'activar', 'eliminar_definitivamente'):
            qs = qs.select_for_update(no_key=self.action != 'eliminar_definitivamente')
        elif self.action == 'stock_minimo' and self.request.method == 'PATCH':
            qs = qs.select_for_update(no_key=True)
        return qs

    def get_serializer_context(self):
        contexto = super().get_serializer_context()
        bodega = getattr(self, 'bodega_catalogo', None)
        contexto['bodega_id'] = bodega['id'] if bodega else None
        return contexto

    def list(self, request, *args, **kwargs):
        respuesta = super().list(request, *args, **kwargs)
        respuesta.data['bodega'] = self.bodega_catalogo
        return respuesta

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ProductoCreateUpdateSerializer
        elif self.action == 'list':
            return ProductoListSerializer
        return ProductoDetailSerializer

    def guardar_producto(self, serializer):
        try:
            with transaction.atomic():
                return serializer.save()
        except IntegrityError:
            # Las validaciones previas no sustituyen las restricciones únicas
            # cuando dos personas guardan al mismo tiempo.
            errores = {}
            sku = serializer.validated_data.get('sku')
            repetidos = Producto.objects.filter(sku__iexact=sku) if sku else Producto.objects.none()
            codigos = [c['codigo'] for c in serializer.validated_data.get('codigos_barra', [])]
            conflictos = CodigoBarra.objects.filter(codigo__in=codigos)
            if serializer.instance:
                repetidos = repetidos.exclude(pk=serializer.instance.pk)
                conflictos = conflictos.exclude(producto=serializer.instance)
            if repetidos.exists():
                errores['sku'] = ['Ya existe un producto con este SKU.']
            if conflictos.exists():
                errores['codigos_barra'] = ['Uno de los códigos pertenece a otro producto.']
            if errores:
                raise serializers.ValidationError(errores)
            raise

    def get_permissions(self):
        """Permisos dinámicos según la acción."""
        if self.action == 'create':
            self.permiso_requerido = 'crear_producto'
        elif self.action in ('update', 'partial_update', 'stock_minimo'):
            self.permiso_requerido = 'editar_producto'
        elif self.action in ('destroy', 'activar'):
            self.permiso_requerido = 'eliminar_producto'
        elif self.action == 'eliminar_definitivamente':
            return [IsAuthenticated(), EsAdministrador()]
        return super().get_permissions()

    def notificar_cambio(self, producto, titulo, mensaje, bodega_id=None):
        filtros = {'q': producto.sku}
        if bodega_id is not None:
            filtros['bodega'] = bodega_id
        notificar_administradores(
            tipo='OTRO', titulo=titulo, mensaje=mensaje,
            link='/productos/?' + urlencode(filtros), actor_id=self.request.user.pk,
        )

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(mensaje='Datos inválidos.', errores=serializer.errors)

        producto = self.guardar_producto(serializer)
        registrar_auditoria(
            accion='CREATE',
            modelo='Producto',
            objeto_id=producto.id,
            descripcion=f'Producto creado: {producto.sku} - {producto.nombre}'
        )
        self.notificar_cambio(producto, 'Producto creado', f'Producto «{producto.nombre}» creado. SKU: {producto.sku}.')
        return success_response(
            data=ProductoDetailSerializer(producto).data,
            mensaje='Producto creado exitosamente.',
            status_code=status.HTTP_201_CREATED
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if not serializer.is_valid():
            return error_response(mensaje='Datos inválidos.', errores=serializer.errors)

        producto = self.guardar_producto(serializer)
        registrar_auditoria(
            accion='UPDATE',
            modelo='Producto',
            objeto_id=producto.id,
            descripcion=f'Producto actualizado: {producto.sku}'
        )
        self.notificar_cambio(producto, 'Producto actualizado', f'Datos de «{producto.nombre}» actualizados. SKU: {producto.sku}.')
        return success_response(
            data=ProductoDetailSerializer(producto).data,
            mensaje='Producto actualizado exitosamente.'
        )

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not instance.activo:
            return success_response(mensaje='El producto ya estaba desactivado.')
        instance.desactivar()
        cancelar_alertas_producto(instance)
        registrar_auditoria(
            accion='DEACTIVATE',
            modelo='Producto',
            objeto_id=instance.id,
            descripcion=f'Producto desactivado: {instance.sku}'
        )
        self.notificar_cambio(instance, 'Producto desactivado', f'Producto «{instance.nombre}» desactivado. SKU: {instance.sku}.')
        return success_response(mensaje='Producto desactivado exitosamente.')

    @action(detail=True, methods=['delete'], url_path='eliminar-definitivamente')
    @transaction.atomic
    def eliminar_definitivamente(self, request, pk=None):
        """Solo administradores; nunca borra productos con referencias históricas."""
        producto = self.get_object()
        if tiene_relaciones(producto, ignorar=('codigos_barra',)):
            return error_response(
                mensaje='Este producto tiene registros relacionados. Desactívalo para conservar el historial.',
                status_code=status.HTTP_409_CONFLICT,
            )
        identificador, sku = producto.id, producto.sku
        producto.delete()
        registrar_auditoria(
            accion='DELETE', modelo='Producto', objeto_id=identificador,
            descripcion=f'Producto eliminado definitivamente: {sku}',
        )
        self.notificar_cambio(producto, 'Producto eliminado', f'Producto «{producto.nombre}» eliminado definitivamente. SKU: {sku}.')
        return success_response(mensaje='Producto eliminado definitivamente.')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def activar(self, request, pk=None):
        """Reactiva un producto previamente desactivado."""
        producto = self.get_object()
        if producto.activo:
            return success_response(data=ProductoDetailSerializer(producto).data, mensaje='El producto ya estaba activo.')
        producto.activar()
        registrar_auditoria(
            accion='REACTIVATE',
            modelo='Producto',
            objeto_id=producto.id,
            descripcion=f'Producto reactivado: {producto.sku}'
        )
        self.notificar_cambio(producto, 'Producto reactivado', f'Producto «{producto.nombre}» reactivado. SKU: {producto.sku}.')
        return success_response(
            data=ProductoDetailSerializer(producto).data,
            mensaje='Producto reactivado exitosamente.'
        )

    @action(detail=False, methods=['get'])
    def opciones(self, request):
        bodegas = opciones_bodegas()
        predeterminada = next((b['id'] for b in bodegas if b['nombre'] == 'Bodega Central'), bodegas[0]['id'] if bodegas else None)
        usuario = request.user
        permisos = set(usuario.rol.permisos.values_list('codigo', flat=True)) if usuario.rol_id else set()
        puede = lambda codigo: usuario.is_superuser or codigo in permisos
        admin = es_administrador(usuario)
        return success_response(data={
            'bodegas': bodegas, 'bodega_predeterminada': predeterminada,
            'permisos': {
                'crear': puede('crear_producto'), 'editar': puede('editar_producto'),
                'configurar_minimo': puede('editar_producto'),
                'desactivar': puede('eliminar_producto'), 'reactivar': puede('eliminar_producto'),
                'eliminar_definitivamente': admin, 'auditoria': admin, 'usuarios': admin,
                'configuracion': puede_acceder_admin(usuario),
            },
        })

    @action(detail=True, methods=['get', 'patch'], url_path='stock-minimo')
    @transaction.atomic
    def stock_minimo(self, request, pk=None):
        guardar = request.method == 'PATCH'
        serializer = (GuardarStockMinimoSerializer if guardar else ConsultaStockMinimoSerializer)(
            data=request.data if guardar else request.query_params,
        )
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        producto = self.get_object()
        bodega = obtener_bodega(datos['bodega'], bloquear=guardar)
        registros = StockMinimo.objects.filter(producto=producto, bodega=bodega)
        anterior = registros.aggregate(total=Max('cantidad_minima'))['total']
        minimo = max(0, anterior or 0)
        configurado = anterior is not None
        if guardar:
            minimo = datos['cantidad_minima']
            # El bloqueo del producto serializa las altas de mínimos. Las bases
            # antiguas pueden tener varias filas para la misma pareja; guardar
            # también debe corregir esas filas al bajar o desactivar el mínimo.
            if not configurado or registros.exclude(cantidad_minima=minimo).exists():
                if configurado:
                    registros.update(cantidad_minima=minimo, fecha_modificacion=timezone.now())
                else:
                    StockMinimo.objects.create(producto=producto, bodega=bodega, cantidad_minima=minimo)
                registrar_auditoria(
                    accion='UPDATE', modelo='Producto', objeto_id=producto.pk,
                    descripcion=f'Mínimo de stock de {producto.sku} en {bodega.nombre}: '
                                f'{max(0, anterior or 0)} → {minimo} unidades.',
                    usuario_override=request.user,
                )
                self.notificar_cambio(
                    producto, 'Mínimo de stock actualizado',
                    f'Mínimo de «{producto.nombre}» en {bodega.nombre}: {minimo} unidades. '
                    f'SKU: {producto.sku}.' + (' Aviso de stock bajo desactivado.' if minimo == 0 else ''),
                    bodega_id=bodega.pk,
                )
            configurado = True
        cantidad = anotar_stock(Producto.objects.filter(pk=producto.pk), bodega.pk).values_list('stock_calculado', flat=True).get()
        if guardar:
            evaluar_alerta_sms(producto, bodega)
        return success_response(data={
            'producto_id': producto.pk, 'sku': producto.sku, 'nombre': producto.nombre,
            'bodega_id': bodega.pk, 'bodega': bodega.nombre,
            'stock_actual': cantidad, 'cantidad_minima': minimo,
            'configurado': configurado, 'alerta_stock_bajo_activa': minimo > 0,
            'estado_stock': estado_stock(cantidad, minimo),
        }, mensaje='Mínimo guardado.' if guardar else 'Mínimo de stock por bodega.')

    @action(detail=False, methods=['get'])
    def buscar(self, request):
        """
        Búsqueda de productos por SKU, nombre o código de barras.

        GET /api/v1/productos/buscar/?q=texto
        """
        q = request.query_params.get('q', '').strip()
        if not q:
            return error_response(mensaje='Debe proporcionar un término de búsqueda.')

        productos = self.get_queryset().filter(
            Q(sku__icontains=q) |
            Q(nombre__icontains=q) |
            Q(codigos_barra__codigo__icontains=q),
            activo=True
        ).distinct()[:20]

        serializer = ProductoListSerializer(productos, many=True, context=self.get_serializer_context())
        return success_response(data=serializer.data)

    @action(detail=False, methods=['get'], url_path='por-codigo/(?P<codigo>[^/.]+)')
    def por_codigo(self, request, codigo=None):
        """
        Busca un producto por su código de barras exacto.
        Endpoint usado por el escaneo de códigos.

        GET /api/v1/productos/por-codigo/{codigo}/
        """
        try:
            codigo_barra = CodigoBarra.objects.select_related('producto').get(
                codigo=codigo,
                producto__activo=True
            )
        except CodigoBarra.DoesNotExist:
            return error_response(
                mensaje='Producto no encontrado.',
                status_code=status.HTTP_404_NOT_FOUND
            )

        serializer = ProductoDetailSerializer(codigo_barra.producto)
        return success_response(data=serializer.data)
