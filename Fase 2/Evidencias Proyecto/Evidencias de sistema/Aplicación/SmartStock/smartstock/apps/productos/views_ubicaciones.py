"""Estructura física y referencias de productos; el stock pertenece a la bodega."""
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination

from apps.core.responses import error_response, success_response
from apps.core.utils import registrar_auditoria
from .bodegas import opciones_bodegas
from .models import Bodega, Estanteria, Nivel, Pasillo, Producto, ProductoUbicacion, Ubicacion
from .views_dashboard import permisos_dashboard
from .views_notificaciones import notificar_administradores


def capacidades(usuario):
    activo = usuario.is_authenticated and usuario.activo and (
        usuario.is_superuser or bool(usuario.rol_id and usuario.rol.activo))
    admin = activo and (usuario.is_superuser or usuario.rol.codigo == 'administrador')
    return {
        'ver': bool(activo and (admin or usuario.tiene_permiso('ver_bodega'))),
        'gestionar': bool(activo and (admin or usuario.tiene_permiso('editar_bodega'))),
    }


class AccesoUbicaciones(permissions.BasePermission):
    message = 'No tienes permiso para gestionar las ubicaciones de la bodega.'

    def has_permission(self, request, view):
        p = capacidades(request.user)
        return p['ver'] and (request.method in permissions.SAFE_METHODS or p['gestionar'])


class PaginasUbicaciones(PageNumberPagination):
    page_size = 25


class ConsultaUbicaciones(serializers.Serializer):
    bodega = serializers.IntegerField(min_value=1)
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)
    producto = serializers.IntegerField(required=False, min_value=1)
    ubicacion = serializers.IntegerField(required=False, min_value=1)


def consulta(request, *, bloquear=False):
    s = ConsultaUbicaciones(data=request.query_params.dict())
    s.is_valid(raise_exception=True)
    qs = Bodega.objects.select_for_update() if bloquear else Bodega.objects.all()
    bodega = get_object_or_404(qs, pk=s.validated_data['bodega'])
    if bloquear and not bodega.activa:
        raise ValidationError({'bodega': 'Las ubicaciones de una bodega inactiva son de solo lectura.'})
    return bodega, s.validated_data


class DatosEstrictos(serializers.Serializer):
    def validate(self, attrs):
        extra = set(self.initial_data) - set(self.fields)
        if extra:
            raise ValidationError({k: 'Este campo no está permitido.' for k in sorted(extra)})
        return attrs


class CodigoUbicacion(DatosEstrictos):
    codigo = serializers.CharField(max_length=20)

    def validate_codigo(self, valor):
        valor = ' '.join(valor.split()).upper()
        if not valor or not all(c.isprintable() for c in valor):
            raise ValidationError('Ingresa un código válido de hasta 20 caracteres.')
        return valor


# Las relaciones no se pueden cambiar al editar: mover una estructura a otra
# bodega alteraría también las referencias de todos sus productos.
ESTRUCTURA = {
    'pasillos': (Pasillo, 'bodega', Bodega, '', 'estanterias'),
    'estanterias': (Estanteria, 'pasillo', Pasillo, 'pasillo__bodega', 'niveles'),
    'niveles': (Nivel, 'estanteria', Estanteria, 'estanteria__pasillo__bodega', 'ubicaciones'),
    'espacios': (Ubicacion, 'nivel', Nivel, 'nivel__estanteria__pasillo__bodega', 'productoubicacion'),
}
RUTA_UBICACION = 'nivel__estanteria__pasillo__bodega'


def ruta(ubicacion):
    nivel = ubicacion.nivel
    estante = nivel.estanteria
    return {'pasillo': estante.pasillo.codigo, 'estanteria': estante.codigo,
            'nivel': nivel.codigo, 'ubicacion': ubicacion.codigo}


def describir(ubicacion):
    return ' / '.join(ruta(ubicacion).values())


def registrar(request, modelo, pk, accion, texto):
    registrar_auditoria(accion=accion, modelo=modelo, objeto_id=pk,
                       descripcion=texto, usuario_override=request.user)
    notificar_administradores(tipo='OTRO', titulo='Ubicación física actualizada', mensaje=texto,
                             link='/ubicaciones/?bodega=' + str(int(request.query_params['bodega'])),
                             actor_id=request.user.pk)


@method_decorator(never_cache, name='dispatch')
class EstructuraViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated, AccesoUbicaciones]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def configuracion(self):
        return ESTRUCTURA[self.basename]

    def objetos(self, bodega):
        modelo, _, _, camino, hijos = self.configuracion()
        filtro = {camino: bodega} if camino else {'bodega': bodega}
        return modelo.objects.filter(**filtro).annotate(elementos=Count(hijos)).order_by('codigo', 'id')

    def datos(self, objeto):
        return {'id': objeto.pk, 'codigo': objeto.codigo,
                'padre_id': getattr(objeto, self.configuracion()[1] + '_id'),
                'elementos': objeto.elementos}

    def list(self, request):
        bodega, datos = consulta(request)
        _, padre, _, _, _ = self.configuracion()
        qs = self.objetos(bodega)
        if padre != 'bodega':
            campo = serializers.IntegerField(min_value=1)
            padre_id = campo.run_validation(request.query_params.get(padre))
            self.obtener_padre(bodega, padre_id)
            qs = qs.filter(**{padre + '_id': padre_id})
        if datos.get('search'):
            qs = qs.filter(codigo__icontains=datos['search'])
        paginador = PaginasUbicaciones()
        filas = paginador.paginate_queryset(qs, request)
        return paginador.get_paginated_response([self.datos(o) for o in filas])

    def obtener_padre(self, bodega, identificador):
        _, padre, modelo_padre, camino, _ = self.configuracion()
        if padre == 'bodega':
            return bodega
        camino = camino.removeprefix(padre + '__')
        return get_object_or_404(modelo_padre, pk=identificador, **{camino: bodega})

    @transaction.atomic
    def create(self, request):
        bodega, _ = consulta(request, bloquear=True)
        modelo, padre, _, _, _ = self.configuracion()
        s = CodigoUbicacion(data=request.data)
        if padre != 'bodega':
            s.fields[padre] = serializers.IntegerField(min_value=1)
        s.is_valid(raise_exception=True)
        superior = self.obtener_padre(bodega, s.validated_data.get(padre))
        codigo = s.validated_data['codigo']
        # Todas las escrituras de estructura/asignaciones toman la misma bodega.
        # Así se serializa también el primer alta sin modificar datos heredados.
        if modelo.objects.filter(**{padre: superior}, codigo__iexact=codigo).exists():
            raise ValidationError({'codigo': 'Este código ya existe dentro de la misma estructura.'})
        objeto = modelo.objects.create(**{padre: superior, 'codigo': codigo})
        registrar(request, modelo.__name__, objeto.pk, 'CREATE', f'{modelo.__name__} creado: {codigo}. Bodega: {bodega.nombre}.')
        return success_response(self.datos(self.objetos(bodega).get(pk=objeto.pk)), 'Estructura creada.', 201)

    @transaction.atomic
    def partial_update(self, request, pk=None):
        bodega, _ = consulta(request, bloquear=True)
        modelo, padre, _, _, _ = self.configuracion()
        objeto = get_object_or_404(self.objetos(bodega), pk=pk)
        s = CodigoUbicacion(data=request.data)
        s.is_valid(raise_exception=True)
        codigo = s.validated_data['codigo']
        if modelo.objects.filter(**{padre + '_id': getattr(objeto, padre + '_id')}, codigo__iexact=codigo).exclude(pk=pk).exists():
            raise ValidationError({'codigo': 'Este código ya existe dentro de la misma estructura.'})
        anterior = objeto.codigo
        objeto.codigo = codigo
        objeto.save(update_fields=['codigo', 'fecha_modificacion'])
        if anterior != codigo:
            registrar(request, modelo.__name__, objeto.pk, 'UPDATE', f'{modelo.__name__}: {anterior} → {codigo}. Bodega: {bodega.nombre}.')
        return success_response(self.datos(objeto), 'Código actualizado.')

    @transaction.atomic
    def destroy(self, request, pk=None):
        bodega, _ = consulta(request, bloquear=True)
        modelo, _, _, _, hijos = self.configuracion()
        objeto = get_object_or_404(self.objetos(bodega), pk=pk)
        relaciones = objeto.productoubicacion_set if hijos == 'productoubicacion' else getattr(objeto, hijos)
        if relaciones.exists():
            return error_response('No se puede eliminar: contiene estructura o productos asignados. Retira primero sus referencias.', status_code=409)
        registrar(request, modelo.__name__, objeto.pk, 'DELETE', f'{modelo.__name__} eliminado: {objeto.codigo}. Bodega: {bodega.nombre}.')
        objeto.delete()
        return success_response(mensaje='Elemento vacío eliminado.')


@never_cache
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def opciones_ubicaciones(request):
    p = capacidades(request.user)
    return success_response({'permisos': p, 'menu': permisos_dashboard(request.user),
                             'bodegas': opciones_bodegas(incluir_inactivas=True) if p['ver'] else []})


@never_cache
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, AccesoUbicaciones])
def productos_ubicaciones(request):
    _, datos = consulta(request)
    qs = Producto.objects.all().order_by('nombre', 'id')
    if datos.get('producto'):
        qs = qs.filter(pk=datos['producto'])
    if datos.get('search'):
        texto = datos['search']
        qs = qs.filter(Q(nombre__icontains=texto) | Q(sku__icontains=texto) | Q(codigos_barra__codigo__icontains=texto)).distinct()
    paginador = PaginasUbicaciones()
    filas = paginador.paginate_queryset(qs, request)
    return paginador.get_paginated_response([{'id': o.pk, 'nombre': o.nombre, 'sku': o.sku, 'activo': o.activo} for o in filas])


def asignaciones(bodega):
    return ProductoUbicacion.objects.filter(**{'ubicacion__' + RUTA_UBICACION: bodega}).select_related(
        'producto', 'ubicacion__nivel__estanteria__pasillo').order_by('producto__nombre', 'ubicacion__codigo', 'id')


def datos_asignacion(objeto):
    return {'id': objeto.pk, 'producto_id': objeto.producto_id, 'producto': objeto.producto.nombre,
            'sku': objeto.producto.sku, 'activo': objeto.producto.activo,
            'ubicacion_id': objeto.ubicacion_id, 'ruta': ruta(objeto.ubicacion),
            'cantidad_heredada': objeto.cantidad}


class NuevaAsignacion(DatosEstrictos):
    producto_id = serializers.IntegerField(min_value=1)
    ubicacion_id = serializers.IntegerField(min_value=1)


@never_cache
@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated, AccesoUbicaciones])
def asignaciones_ubicaciones(request):
    if request.method == 'GET':
        bodega, datos = consulta(request)
        qs = asignaciones(bodega)
        if datos.get('producto'):
            qs = qs.filter(producto_id=datos['producto'])
        if datos.get('ubicacion'):
            get_object_or_404(Ubicacion, pk=datos['ubicacion'], **{RUTA_UBICACION: bodega})
            qs = qs.filter(ubicacion_id=datos['ubicacion'])
        if datos.get('search'):
            texto = datos['search']
            qs = qs.filter(Q(producto__nombre__icontains=texto) | Q(producto__sku__icontains=texto)
                           | Q(ubicacion__codigo__icontains=texto) | Q(ubicacion__nivel__codigo__icontains=texto)
                           | Q(ubicacion__nivel__estanteria__codigo__icontains=texto)
                           | Q(ubicacion__nivel__estanteria__pasillo__codigo__icontains=texto)
                           | Q(producto__codigos_barra__codigo__icontains=texto)).distinct()
        paginador = PaginasUbicaciones()
        filas = paginador.paginate_queryset(qs, request)
        return paginador.get_paginated_response([datos_asignacion(o) for o in filas])
    with transaction.atomic():
        s = NuevaAsignacion(data=request.data)
        s.is_valid(raise_exception=True)
        producto = get_object_or_404(Producto.objects.select_for_update(no_key=True), pk=s.validated_data['producto_id'])
        bodega, _ = consulta(request, bloquear=True)
        if not producto.activo:
            raise ValidationError({'producto_id': 'Reactiva el producto antes de asignarle una ubicación.'})
        espacio = get_object_or_404(Ubicacion.objects.select_related('nivel__estanteria__pasillo'),
                                   pk=s.validated_data['ubicacion_id'], **{RUTA_UBICACION: bodega})
        objeto = ProductoUbicacion.objects.filter(producto=producto, ubicacion=espacio).order_by('id').first()
        if objeto is not None:
            return success_response(datos_asignacion(asignaciones(bodega).get(pk=objeto.pk)), 'El producto ya está asignado a esta ubicación.')
        objeto = ProductoUbicacion.objects.create(producto=producto, ubicacion=espacio, cantidad=0)
        registrar(request, 'ProductoUbicacion', objeto.pk, 'CREATE',
                  f'Ubicación asignada a {producto.nombre} ({producto.sku}): {bodega.nombre} / {describir(espacio)}. Referencia sin modificar stock.')
        return success_response(datos_asignacion(asignaciones(bodega).get(pk=objeto.pk)), 'Ubicación asignada.', 201)


@never_cache
@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated, AccesoUbicaciones])
@transaction.atomic
def retirar_asignacion(request, pk):
    bodega, _ = consulta(request)
    referencia = get_object_or_404(asignaciones(bodega), pk=pk)
    # Mismo orden de bloqueos que movimientos: producto y después bodega.
    Producto.objects.select_for_update(no_key=True).get(pk=referencia.producto_id)
    bodega, _ = consulta(request, bloquear=True)
    objeto = get_object_or_404(asignaciones(bodega), pk=pk)
    if objeto.cantidad != 0:
        return error_response('Esta referencia contiene cantidades de una distribución anterior. Requiere revisión antes de retirarla para conservar esas unidades.', status_code=409)
    registrar(request, 'ProductoUbicacion', objeto.pk, 'DELETE',
              f'Ubicación retirada de {objeto.producto.nombre} ({objeto.producto.sku}): {bodega.nombre} / {describir(objeto.ubicacion)}. Sin modificar stock.')
    objeto.delete()
    return success_response(mensaje='Referencia de ubicación retirada.')
