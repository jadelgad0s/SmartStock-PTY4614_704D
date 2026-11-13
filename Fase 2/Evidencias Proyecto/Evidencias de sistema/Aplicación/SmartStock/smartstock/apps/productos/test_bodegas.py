"""Administración y operaciones usando únicamente el modelo Bodega vigente."""
from unittest.mock import patch

from django.apps import apps
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.usuarios.models import Permiso, Rol, Usuario
from .models import (
    Bodega, Estanteria, Merma, Movimiento, Nivel, Notificacion, Pasillo,
    Producto, ProductoUbicacion, StockBodega, Transferencia, Ubicacion,
)

API = '/api/v1/'
PRODUCTOS = API + 'productos/'


@override_settings(SMS_ALERTAS_ACTIVAS=False)
class BodegasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol = Rol.objects.create(codigo='administrador', nombre='Administrador')
        for codigo in ('registrar_entrada', 'registrar_salida', 'registrar_merma', 'editar_producto'):
            cls.rol.permisos.add(Permiso.objects.create(codigo=codigo, nombre=codigo, modulo='inventario'))
        cls.usuario = Usuario.objects.create_user(email='bodegas@example.com', rol=cls.rol, nombres='Persona', apellidos='Prueba')
        cls.central = Bodega.objects.create(nombre='Bodega Central', direccion='Dirección antigua')
        cls.otra = Bodega.objects.create(nombre='Bodega Norte', direccion='Calle Norte 123')
        cls.producto = Producto.objects.create(sku='MULTI-1', nombre='Producto compartido')
        cls.stock = StockBodega.objects.create(producto=cls.producto, bodega=cls.central, cantidad_total=24)
        cls.stock_otro = StockBodega.objects.create(producto=cls.producto, bodega=cls.otra, cantidad_total=10)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)

    def nueva_bodega(self, **datos):
        return self.client.post(API + 'bodegas/', {'nombre': 'Depósito', **datos}, format='json')

    def mover(self, bodega=None, **datos):
        return self.client.post(PRODUCTOS + 'registrar-movimiento/', {
            'bodega_id': (bodega or self.otra).pk, 'producto_id': self.producto.pk,
            'tipo_movimiento': 'SALIDA', 'cantidad': 3, **datos,
        }, format='json')

    def merma(self, bodega=None, **datos):
        return self.client.post(PRODUCTOS + 'mermas/', {
            'bodega_id': (bodega or self.otra).pk, 'producto_id': self.producto.pk,
            'cantidad': 1, 'motivo': 'DAÑO', 'observacion': 'Envase roto.', **datos,
        }, format='json')

    def test_solo_se_utiliza_la_tabla_bodegas_sin_nuevas_relaciones(self):
        self.assertIn('bodegas', connection.introspection.table_names())
        self.assertNotIn('sucursales', connection.introspection.table_names())
        self.assertNotIn('sucursal', {f.name for f in Bodega._meta.fields})
        with self.assertRaises(LookupError):
            apps.get_model('productos', 'Sucursal')
        self.assertEqual(self.client.get(API + 'sucursales/').status_code, 404)
        self.assertEqual(Bodega.objects.count(), 2)

    def test_crear_normaliza_y_registra_auditoria_y_campana(self):
        r = self.nueva_bodega(nombre='  Depósito   Principal  ')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['data']['nombre'], 'Depósito Principal')
        self.assertEqual(r.data['data']['direccion'], '')
        self.assertEqual(r.data['data']['unidades'], 0)
        self.assertTrue(Auditoria.objects.filter(modelo='Bodega', accion='CREATE').exists())
        self.assertTrue(Notificacion.objects.filter(usuario_destino=self.usuario, link='/bodegas/').exists())

    def test_nombres_invalidos_duplicados_y_campos_ajenos_se_rechazan(self):
        for datos in ({'nombre': '   '}, {'nombre': 'bodega NORTE'}, {'nombre': 'x' * 101},
                      {'direccion': 'x' * 201}, {'codigo': 'CAMPO-AJENO'}):
            with self.subTest(datos=datos):
                self.assertEqual(self.nueva_bodega(**datos).status_code, 400)
        self.assertEqual(Bodega.objects.count(), 2)
        self.assertFalse(Auditoria.objects.exists())

    def test_editar_conserva_id_existencias_e_historial_y_describe_cambios(self):
        self.mover()
        movimiento_id = Movimiento.objects.get().pk
        r = self.client.patch(API + f'bodegas/{self.otra.pk}/', {'nombre': 'Depósito Norte', 'direccion': 'Calle Nueva 456'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.otra.refresh_from_db()
        self.stock_otro.refresh_from_db()
        self.assertEqual(self.otra.nombre, 'Depósito Norte')
        self.assertEqual(self.otra.direccion, 'Calle Nueva 456')
        self.assertEqual(self.stock_otro.cantidad_total, 7)
        self.assertEqual(Movimiento.objects.get(pk=movimiento_id).bodega_id, self.otra.pk)
        self.assertEqual(r.data['data']['unidades'], 7)
        audit = Auditoria.objects.get(modelo='Bodega')
        self.assertIn('Nombre: Bodega Norte → Depósito Norte', audit.descripcion)
        self.assertIn('Dirección: Calle Norte 123 → Calle Nueva 456', audit.descripcion)

    def test_central_conserva_su_nombre_para_clientes_anteriores(self):
        ruta = API + f'bodegas/{self.central.pk}/'
        self.assertEqual(self.client.patch(ruta, {'nombre': 'Otro nombre'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(ruta, {'direccion': 'Nueva dirección'}, format='json').status_code, 200)
        self.central.refresh_from_db()
        self.assertEqual(self.central.nombre, 'Bodega Central')
        self.assertEqual(self.central.direccion, 'Nueva dirección')
        self.assertEqual(StockBodega.objects.get(pk=self.stock.pk).cantidad_total, 24)

    def test_nombres_repetidos_heredados_permiten_editar_direccion(self):
        otra = Bodega.objects.create(nombre=self.otra.nombre)
        r = self.client.patch(API + f'bodegas/{otra.pk}/', {'nombre': otra.nombre, 'direccion': 'Dirección completa'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Bodega.objects.filter(nombre=self.otra.nombre).count(), 2)

    def test_estado_no_se_desactiva_mediante_patch(self):
        r = self.client.patch(API + f'bodegas/{self.otra.pk}/', {'activa': False}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.otra.refresh_from_db()
        self.assertTrue(self.otra.activa)

    def test_lectura_orden_paginacion_filtros_y_totales_sin_multiplicar(self):
        StockBodega.objects.filter(producto=self.producto, bodega=self.otra).update(cantidad_total=12)
        r = self.client.get(API + 'bodegas/', {'activa': 'true', 'search': 'Calle Norte'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['unidades'], 12)
        Bodega.objects.bulk_create([Bodega(nombre=f'Depósito {i:02d}', activa=i != 0) for i in range(30)])
        primera = self.client.get(API + 'bodegas/')
        segunda = self.client.get(API + 'bodegas/', {'page': 2})
        self.assertEqual(primera.data['count'], 32)
        self.assertEqual(len(primera.data['results']), 25)
        self.assertEqual(len(segunda.data['results']), 7)
        self.assertFalse({r['id'] for r in primera.data['results']} & {r['id'] for r in segunda.data['results']})
        self.assertEqual(self.client.get(API + 'bodegas/', {'activa': 'false'}).data['count'], 1)
        self.assertIn('no-store', primera['Cache-Control'])

    def test_filtros_invalidos_devuelven_error(self):
        for datos in ({'activa': 'quizás'}, {'search': 'x' * 201}):
            self.assertEqual(self.client.get(API + 'bodegas/', datos).status_code, 400)

    def test_lector_no_puede_modificar_y_permisos_bodega_conceden_acciones(self):
        lector = Rol.objects.create(codigo='lector', nombre='Lector')
        lector.permisos.add(Permiso.objects.create(codigo='ver_bodega', nombre='Ver bodegas', modulo='bodegas'))
        self.usuario.rol = lector
        self.usuario.save(update_fields=['rol'])
        self.assertEqual(self.client.get(API + 'bodegas/').status_code, 200)
        self.assertEqual(self.client.get(API + 'bodegas/opciones/').status_code, 200)
        self.assertEqual(self.nueva_bodega().status_code, 403)
        for codigo in ('crear_bodega', 'editar_bodega', 'eliminar_bodega'):
            lector.permisos.add(Permiso.objects.create(codigo=codigo, nombre=codigo, modulo='bodegas'))
        self.assertEqual(self.nueva_bodega().status_code, 201)
        self.assertEqual(self.client.patch(API + f'bodegas/{self.otra.pk}/', {'nombre': 'Nuevo nombre'}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(API + f'bodegas/{self.otra.pk}/').status_code, 409)

    def test_usuario_inactivo_y_anonimo_no_acceden(self):
        self.usuario.activo = False
        for ruta in ('bodegas/', 'bodegas/opciones/'):
            self.assertEqual(self.client.get(API + ruta).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(API + 'bodegas/').status_code, 401)

    def test_baja_con_unidades_no_elimina_datos_incluso_producto_inactivo(self):
        Producto.objects.filter(pk=self.producto.pk).update(activo=False)
        r = self.client.delete(API + f'bodegas/{self.otra.pk}/')
        self.assertEqual(r.status_code, 409)
        self.otra.refresh_from_db()
        self.assertTrue(self.otra.activa)
        self.assertEqual(StockBodega.objects.get(pk=self.stock_otro.pk).cantidad_total, 10)
        self.assertFalse(Auditoria.objects.exists())

    def test_baja_reactivacion_idempotentes_y_historial_conservado(self):
        self.mover(cantidad=10)
        ruta = API + f'bodegas/{self.otra.pk}/'
        self.assertEqual(self.client.delete(ruta).status_code, 200)
        self.assertEqual(self.client.delete(ruta).status_code, 200)
        self.otra.refresh_from_db()
        self.assertFalse(self.otra.activa)
        self.assertTrue(Movimiento.objects.filter(bodega=self.otra).exists())
        self.assertEqual(Auditoria.objects.filter(modelo='Bodega', accion='DEACTIVATE').count(), 1)
        r = self.client.get(PRODUCTOS + 'movimientos/', {'bodega': self.otra.pk})
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['bodega_id'], self.otra.pk)
        self.assertEqual(self.client.post(ruta + 'activar/').status_code, 200)
        self.assertEqual(self.client.post(ruta + 'activar/').status_code, 200)
        self.assertEqual(Auditoria.objects.filter(modelo='Bodega', accion='REACTIVATE').count(), 1)

    def test_baja_rechaza_transferencia_pendiente(self):
        self.stock_otro.delete()
        Transferencia.objects.create(bodega_origen=self.central, bodega_destino=self.otra, usuario=self.usuario, estado='PENDIENTE')
        r = self.client.delete(API + f'bodegas/{self.otra.pk}/')
        self.assertEqual(r.status_code, 409)
        self.assertIn('transferencias', r.data['mensaje'])

    def test_baja_rechaza_unidades_en_ubicaciones(self):
        self.stock_otro.delete()
        pasillo = Pasillo.objects.create(bodega=self.otra, codigo='A')
        estante = Estanteria.objects.create(pasillo=pasillo, codigo='1')
        nivel = Nivel.objects.create(estanteria=estante, codigo='1')
        ubicacion = Ubicacion.objects.create(nivel=nivel, codigo='A-1-1')
        ProductoUbicacion.objects.create(producto=self.producto, ubicacion=ubicacion, cantidad=1)
        r = self.client.delete(API + f'bodegas/{self.otra.pk}/')
        self.assertEqual(r.status_code, 409)
        self.assertIn('ubicaciones', r.data['mensaje'])

    def test_fallo_auditoria_revierte_alta_cambio_y_baja(self):
        vacia = Bodega.objects.create(nombre='Vacía')
        with patch('apps.productos.views_bodegas.registrar_auditoria', side_effect=RuntimeError('prueba')):
            for metodo, ruta, datos in (
                ('post', 'bodegas/', {'nombre': 'Falla'}),
                ('patch', f'bodegas/{self.otra.pk}/', {'nombre': 'No guardar'}),
                ('delete', f'bodegas/{vacia.pk}/', {}),
            ):
                with self.subTest(metodo=metodo), self.assertLogs('django.request', level='ERROR'), self.assertRaises(RuntimeError):
                    getattr(self.client, metodo)(API + ruta, datos, format='json')
        self.assertFalse(Bodega.objects.filter(nombre='Falla').exists())
        self.otra.refresh_from_db(); vacia.refresh_from_db()
        self.assertEqual(self.otra.nombre, 'Bodega Norte')
        self.assertTrue(vacia.activa)
        self.assertFalse(Notificacion.objects.exists())

    def test_opciones_excluye_inactivas_y_el_catalogo_usa_el_mismo_contexto(self):
        antigua = Bodega.objects.create(nombre='Antigua', activa=False)
        r = self.client.get(API + 'bodegas/opciones/').data['data']
        self.assertEqual([b['id'] for b in r['bodegas']], [self.central.pk, self.otra.pk])
        self.assertEqual(r['bodega_predeterminada'], self.central.pk)
        self.assertEqual({b['id'] for b in r['bodegas_historial']}, {self.central.pk, self.otra.pk, antigua.pk})
        self.assertNotIn('sucursales', r)
        self.assertTrue(all(set(b) == {'id', 'nombre', 'activa', 'etiqueta'} for b in r['bodegas']))
        r = self.client.get(PRODUCTOS + 'opciones/').data['data']
        self.assertEqual([b['id'] for b in r['bodegas']], [self.central.pk, self.otra.pk])

    def test_salida_y_merma_usando_otra_bodega_no_modifican_central(self):
        r = self.mover()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['data']['stock_anterior'], 10)
        self.assertEqual(r.data['data']['stock_restante'], 7)
        self.assertEqual(r.data['data']['bodega_id'], self.otra.pk)
        r = self.merma()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['data']['stock_restante'], 6)
        self.stock.refresh_from_db(); self.stock_otro.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 24)
        self.assertEqual(self.stock_otro.cantidad_total, 6)
        self.assertTrue(Auditoria.objects.filter(descripcion__contains='Bodega: Bodega Norte').exists())

    def test_entrada_sin_stock_crea_fila_en_bodega_elegida(self):
        nueva = Bodega.objects.create(nombre='Vacía')
        r = self.mover(nueva, tipo_movimiento='ENTRADA', cantidad=9)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(StockBodega.objects.get(bodega=nueva).cantidad_total, 9)
        self.assertEqual(StockBodega.objects.get(pk=self.stock.pk).cantidad_total, 24)

    def test_resolucion_y_catalogo_mermas_muestran_stock_seleccionado(self):
        for bodega, cantidad in ((self.central, 24), (self.otra, 10)):
            r = self.client.get(PRODUCTOS + 'resolver-movimiento/', {'codigo': 'MULTI-1', 'bodega': bodega.pk})
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(r.data['data']['stock_disponible'], cantidad)
            self.assertEqual(r.data['data']['bodega_id'], bodega.pk)
            r = self.client.get(PRODUCTOS + 'mermas/productos/', {'bodega': bodega.pk})
            self.assertEqual(r.data['results'][0]['stock_disponible'], cantidad)
            self.assertEqual(r.data['results'][0]['bodega_id'], bodega.pk)

    def test_historiales_filtran_bodega_y_conservan_inactivas(self):
        self.mover(self.central); self.mover(self.otra)
        self.merma(self.central); self.merma(self.otra)
        Bodega.objects.filter(pk=self.otra.pk).update(activa=False)
        for ruta in ('movimientos/', 'mermas/historial/'):
            r = self.client.get(PRODUCTOS + ruta, {'bodega': self.otra.pk})
            self.assertEqual(r.data['count'], 1)
            self.assertEqual(r.data['results'][0]['bodega_id'], self.otra.pk)
            self.assertEqual(self.client.get(PRODUCTOS + ruta).data['count'], 2)

    def test_operaciones_rechazan_bodega_inactiva_sin_descontar(self):
        Bodega.objects.filter(pk=self.otra.pk).update(activa=False)
        self.assertEqual(self.mover().status_code, 400)
        self.assertEqual(self.merma().status_code, 400)
        for ruta, datos in (('resolver-movimiento/', {'codigo': 'MULTI-1'}), ('mermas/productos/', {})):
            self.assertEqual(self.client.get(PRODUCTOS + ruta, {**datos, 'bodega': self.otra.pk}).status_code, 400)
        self.assertEqual(StockBodega.objects.get(pk=self.stock_otro.pk).cantidad_total, 10)
        self.assertFalse(Movimiento.objects.exists()); self.assertFalse(Merma.objects.exists())

    def test_ids_invalidos_no_caen_silenciosamente_a_central(self):
        for identificador in (0, -1, 999999, True, 'invalida'):
            with self.subTest(identificador=identificador):
                self.assertEqual(self.mover(bodega_id=identificador).status_code, 400)
                self.assertEqual(self.merma(bodega_id=identificador).status_code, 400)
        self.assertFalse(Movimiento.objects.exists()); self.assertFalse(Merma.objects.exists())

    def test_operaciones_conservan_una_fila_en_la_bodega_operada(self):
        StockBodega.objects.filter(pk=self.stock_otro.pk).update(cantidad_total=12)
        r = self.mover(cantidad=11)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['data']['stock_anterior'], 12)
        self.assertEqual(StockBodega.objects.filter(bodega=self.otra).count(), 1)
        self.assertEqual(StockBodega.objects.get(bodega=self.otra).cantidad_total, 1)
        StockBodega.objects.filter(pk=self.stock_otro.pk).update(cantidad_total=3)
        r = self.merma(cantidad=2)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['data']['stock_anterior'], 3)
        self.assertEqual(StockBodega.objects.get(bodega=self.otra).cantidad_total, 1)
        self.assertEqual(StockBodega.objects.get(pk=self.stock.pk).cantidad_total, 24)

    def test_fallo_auditoria_revierte_stock_y_movimiento(self):
        StockBodega.objects.filter(pk=self.stock_otro.pk).update(cantidad_total=12)
        for modulo, operar in (('views_movimientos', self.mover), ('views_mermas', self.merma)):
            with patch(f'apps.productos.{modulo}.registrar_auditoria', side_effect=RuntimeError('prueba')):
                with self.assertLogs('django.request', level='ERROR'), self.assertRaises(RuntimeError):
                    operar()
            self.assertEqual(list(StockBodega.objects.filter(bodega=self.otra).order_by('id').values_list('cantidad_total', flat=True)), [12])
        self.assertFalse(Movimiento.objects.exists()); self.assertFalse(Merma.objects.exists())

    def test_sin_stock_suficiente_en_bodega_no_usa_total_global(self):
        self.assertEqual(self.mover(cantidad=11).status_code, 409)
        self.assertEqual(self.merma(cantidad=11).status_code, 400)
        self.assertEqual(StockBodega.objects.get(pk=self.stock_otro.pk).cantidad_total, 10)

    def test_sms_evalua_la_bodega_operada(self):
        for modulo, operar in (('views_movimientos', self.mover), ('views_mermas', self.merma)):
            with patch(f'apps.productos.{modulo}.evaluar_alerta_sms') as evaluar:
                self.assertEqual(operar().status_code, 201)
            self.assertEqual(evaluar.call_args.args[0].pk, self.producto.pk)
            self.assertEqual(evaluar.call_args.args[1].pk, self.otra.pk)
