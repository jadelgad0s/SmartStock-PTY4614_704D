"""Administración de las bodegas existentes, con bajas protegidas."""
from django.db import transaction
from django.db.models import IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated, SAFE_METHODS

from apps.core.responses import error_response, success_response
from apps.core.utils import registrar_auditoria
from apps.usuarios.navegacion import es_administrador, puede_acceder_admin
from .bodegas import opciones_bodegas
from .models import Bodega, ProductoUbicacion, StockBodega, Transferencia
from .views_notificaciones import notificar_administradores


def permisos_bodegas(usuario):
    admin = es_administrador(usuario)
    return {**{k: admin or usuario.tiene_permiso(p) for k, p in (
        ('crear', 'crear_bodega'), ('editar', 'editar_bodega'), ('desactivar', 'eliminar_bodega'),
    )}, 'auditoria': admin, 'usuarios': admin,
        'configuracion': puede_acceder_admin(usuario)}


class AccesoBodegas(BasePermission):
    def has_permission(self, request, view):
        usuario = request.user
        if not usuario.is_authenticated or not usuario.activo:
            return False
        if es_administrador(usuario):
            return True
        if request.method in SAFE_METHODS:
            return usuario.tiene_permiso('ver_bodega')
        permiso = {'create': 'crear_bodega', 'update': 'editar_bodega', 'partial_update': 'editar_bodega',
                   'destroy': 'eliminar_bodega', 'activar': 'eliminar_bodega'}.get(view.action)
        return bool(permiso and usuario.tiene_permiso(permiso))


class BodegasPagination(PageNumberPagination):
    page_size = 25


class FiltrosBodegasSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)
    activa = serializers.BooleanField(required=False)


class BodegaSerializer(serializers.ModelSerializer):
    unidades = serializers.IntegerField(read_only=True, default=0)
    direccion = serializers.CharField(max_length=200, allow_blank=True, required=False, default='')

    class Meta:
        model = Bodega
        fields = ('id', 'nombre', 'direccion', 'activa', 'unidades')
        read_only_fields = ('id', 'activa')

    def validate_nombre(self, valor):
        valor = ' '.join(valor.split())
        if self.instance and self.instance.nombre == 'Bodega Central' and valor != 'Bodega Central':
            raise serializers.ValidationError('Bodega Central es la bodega predeterminada y debe conservar su nombre.')
        # Los nombres repetidos heredados no impiden editar otros datos.
        if self.instance and valor == ' '.join(self.instance.nombre.split()):
            return valor
        qs = Bodega.objects.filter(nombre__iexact=valor)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Ya existe una bodega con este nombre.')
        return valor

    def validate(self, attrs):
        desconocidos = set(self.initial_data) - set(self.fields)
        if desconocidos:
            raise serializers.ValidationError({campo: 'Este campo no está permitido.' for campo in desconocidos})
        return attrs


@method_decorator(never_cache, name='dispatch')
class BodegaViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, AccesoBodegas]
    pagination_class = BodegasPagination
    serializer_class = BodegaSerializer
    http_method_names = ['get', 'post', 'patch', 'put', 'delete', 'head', 'options']
    cantidad = StockBodega.objects.filter(bodega_id=OuterRef('pk')).order_by().values('bodega_id').annotate(n=Sum('cantidad_total')).values('n')
    queryset = Bodega.objects.annotate(unidades=Coalesce(Subquery(cantidad, output_field=IntegerField()), Value(0)))

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'list':
            # Un QueryDict convertiría la ausencia del BooleanField en False.
            filtros = FiltrosBodegasSerializer(data=self.request.query_params.dict())
            filtros.is_valid(raise_exception=True)
            datos = filtros.validated_data
            if datos.get('search'):
                qs = qs.filter(Q(nombre__icontains=datos['search']) | Q(direccion__icontains=datos['search']))
            if 'activa' in datos:
                qs = qs.filter(activa=datos['activa'])
        return qs.order_by('nombre', 'id')

    def registrar(self, objeto, accion, texto):
        registrar_auditoria(accion=accion, modelo='Bodega', objeto_id=objeto.pk,
                           descripcion=texto, usuario_override=self.request.user)
        titulo = 'Bodega ' + {'CREATE': 'creada', 'UPDATE': 'actualizada', 'DEACTIVATE': 'desactivada', 'REACTIVATE': 'reactivada'}[accion]
        notificar_administradores(tipo='OTRO', titulo=titulo, mensaje=texto,
                                 link='/bodegas/', actor_id=self.request.user.pk)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        objeto = serializer.save()
        self.registrar(objeto, 'CREATE', f'Bodega creada: {objeto.nombre}.')
        return success_response(data=self.get_serializer(self.get_queryset().get(pk=objeto.pk)).data,
                                mensaje='Bodega creada.', status_code=status.HTTP_201_CREATED)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        objeto = Bodega.objects.select_for_update().get(pk=self.get_object().pk)
        serializer = self.get_serializer(objeto, data=request.data, partial=kwargs.pop('partial', False))
        serializer.is_valid(raise_exception=True)
        anteriores = {'nombre': objeto.nombre, 'direccion': objeto.direccion}
        objeto = serializer.save()
        etiquetas = {'nombre': 'Nombre', 'direccion': 'Dirección'}
        cambios = [f'{etiquetas[c]}: {a or "Sin dirección"} → {getattr(objeto, c) or "Sin dirección"}'
                   for c, a in anteriores.items() if a != getattr(objeto, c)]
        descripcion = f'Bodega actualizada: {objeto.nombre}.'
        self.registrar(objeto, 'UPDATE', descripcion + (' ' + '; '.join(cambios) + '.' if cambios else ' Sin cambios de datos.'))
        return success_response(data=self.get_serializer(self.get_queryset().get(pk=objeto.pk)).data, mensaje='Bodega actualizada.')

    def bloqueo_desactivacion(self, objeto):
        if StockBodega.objects.filter(bodega=objeto).exclude(cantidad_total=0).exists():
            return 'La bodega tiene existencias. Debe quedar sin unidades antes de desactivarla.'
        if ProductoUbicacion.objects.filter(ubicacion__nivel__estanteria__pasillo__bodega=objeto).exclude(cantidad=0).exists():
            return 'La bodega tiene unidades asignadas a ubicaciones. Revisa sus existencias.'
        if Transferencia.objects.filter(Q(bodega_origen=objeto) | Q(bodega_destino=objeto), estado='PENDIENTE').exists():
            return 'La bodega tiene transferencias pendientes.'
        return ''

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        objeto = Bodega.objects.select_for_update().get(pk=self.get_object().pk)
        if not objeto.activa:
            return success_response(mensaje='La bodega ya estaba desactivada.')
        bloqueo = self.bloqueo_desactivacion(objeto)
        if bloqueo:
            return error_response(bloqueo, status_code=409)
        objeto.activa = False
        objeto.save(update_fields=['activa', 'fecha_modificacion'])
        self.registrar(objeto, 'DEACTIVATE', f'Bodega desactivada: {objeto.nombre}.')
        return success_response(mensaje='Bodega desactivada.')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def activar(self, request, pk=None):
        objeto = Bodega.objects.select_for_update().get(pk=self.get_object().pk)
        if objeto.activa:
            return success_response(mensaje='La bodega ya estaba activa.')
        objeto.activa = True
        objeto.save(update_fields=['activa', 'fecha_modificacion'])
        self.registrar(objeto, 'REACTIVATE', f'Bodega reactivada: {objeto.nombre}.')
        return success_response(mensaje='Bodega reactivada.')

    @action(detail=False, methods=['get'])
    def opciones(self, request):
        activas = opciones_bodegas()
        return success_response(data={
            'bodegas': activas, 'bodegas_historial': opciones_bodegas(incluir_inactivas=True),
            'bodega_predeterminada': next((b['id'] for b in activas if b['nombre'] == 'Bodega Central'), activas[0]['id'] if activas else None),
            'permisos': permisos_bodegas(request.user),
            'operar': {k: request.user.tiene_permiso(p) for k, p in (
                ('entrada', 'registrar_entrada'), ('salida', 'registrar_salida'), ('merma', 'registrar_merma'),
            )},
        })
