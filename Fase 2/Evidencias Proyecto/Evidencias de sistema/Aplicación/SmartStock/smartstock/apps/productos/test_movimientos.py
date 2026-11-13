"""Historial completo, resolución exacta y registro atómico de stock."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.usuarios.models import Permiso, Rol, Usuario
from .models import Bodega, CodigoBarra, DetalleMovimiento, Movimiento, Producto, StockBodega, TipoMovimiento

ROOT = '/api/v1/productos/'


def preparar_usuario():
    rol = Rol.objects.create(nombre='Operador movimientos', codigo='operador')
    for codigo in ('ver_movimiento', 'registrar_entrada', 'registrar_salida'):
        rol.permisos.add(Permiso.objects.create(codigo=codigo, nombre=codigo, modulo='movimientos'))
    return Usuario.objects.create_user(
        email='movimientos@example.com', password='PasswordSeguro123!',
        nombres='Persona', apellidos='Prueba', rol=rol,
    )


class RegistroMovimientosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = preparar_usuario()
        cls.bodega = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        cls.producto = Producto.objects.create(sku='MOV-001', nombre='Bebida Cherry')
        cls.stock = StockBodega.objects.create(producto=cls.producto, bodega=cls.bodega, cantidad_total=10)
        otra = Bodega.objects.create(nombre='Otra bodega', direccion='Otra')
        StockBodega.objects.create(producto=cls.producto, bodega=otra, cantidad_total=90)
        CodigoBarra.objects.create(producto=cls.producto, codigo='COD/780.001', es_principal=False)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)

    def registrar(self, **cambios):
        return self.client.post(ROOT + 'registrar-movimiento/', {
            'producto_id': self.producto.pk, 'tipo_movimiento': 'SALIDA',
            'cantidad': 3, 'observacion': 'Guía 123', **cambios,
        }, format='json')

    def test_salida_descuenta_stock_y_guarda_detalle_auditoria(self):
        respuesta = self.registrar()
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 7)
        self.assertEqual(respuesta.data['data']['stock_anterior'], 10)
        self.assertEqual(respuesta.data['data']['stock_restante'], 7)
        mov = Movimiento.objects.get()
        self.assertEqual(mov.documento_referencia, 'Guía 123')
        self.assertEqual(mov.usuario, self.usuario)
        self.assertEqual(mov.detalles.get().cantidad, 3)
        self.assertTrue(Auditoria.objects.filter(modelo='Movimiento', objeto_id=str(mov.pk), usuario=self.usuario).exists())

    def test_entrada_suma_y_no_modifica_otras_bodegas(self):
        respuesta = self.registrar(tipo_movimiento='ENTRADA', cantidad=24)
        self.assertEqual(respuesta.status_code, 201)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 34)
        self.assertEqual(StockBodega.objects.exclude(bodega=self.bodega).get().cantidad_total, 90)

    def test_no_descuenta_stock_de_otras_bodegas(self):
        respuesta = self.registrar(cantidad=11)
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data['errores']['stock_disponible'], 10)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 10)
        self.assertEqual(Movimiento.objects.count(), 0)
        self.assertEqual(Auditoria.objects.count(), 0)

    def test_rechaza_cantidades_y_tipos_invalidos_sin_registrar(self):
        for cambios in ({'cantidad': 0}, {'cantidad': -1}, {'cantidad': 1.5},
                        {'cantidad': True}, {'cantidad': 2147483648}, {'tipo_movimiento': 'OTRO'},
                        {'observacion': 'x' * 101}):
            with self.subTest(cambios=cambios):
                self.assertEqual(self.registrar(**cambios).status_code, 400)
        self.assertFalse(Movimiento.objects.exists())
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 10)

    def test_rechaza_entrada_que_desborda_stock(self):
        self.assertEqual(self.registrar(tipo_movimiento='ENTRADA', cantidad=2147483647).status_code, 400)
        self.assertFalse(Movimiento.objects.exists())

    def test_no_existe_o_inactivo_no_se_puede_mover(self):
        self.assertEqual(self.registrar(producto_id=999999).status_code, 404)
        Producto.objects.filter(pk=self.producto.pk).update(activo=False)
        self.assertEqual(self.registrar().status_code, 404)

    def test_resuelve_sku_exacto_y_codigo_secundario_con_stock_de_la_bodega(self):
        # Tener más de 25 productos no debe impedir resolver uno fuera de página.
        Producto.objects.bulk_create([Producto(sku=f'AAA-{i:03d}', nombre=f'A producto {i}') for i in range(55)])
        for codigo in ('MOV-001', 'mov-001', 'COD/780.001'):
            with self.subTest(codigo=codigo):
                respuesta = self.client.get(ROOT + 'resolver-movimiento/', {'codigo': codigo})
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.data['data']['id'], self.producto.pk)
                self.assertEqual(respuesta.data['data']['stock_disponible'], 10)
        self.assertEqual(self.client.get(ROOT + 'resolver-movimiento/', {'codigo': 'MOV'}).status_code, 404)

    def test_primera_entrada_crea_stock_y_salida_sin_stock_no_crea_registros(self):
        nuevo = Producto.objects.create(sku='NUEVO', nombre='Nuevo')
        self.assertEqual(self.registrar(producto_id=nuevo.pk).status_code, 409)
        self.assertFalse(StockBodega.objects.filter(producto=nuevo).exists())
        self.assertEqual(self.registrar(producto_id=nuevo.pk, tipo_movimiento='ENTRADA').status_code, 201)
        self.assertEqual(StockBodega.objects.get(producto=nuevo).cantidad_total, 3)

    def test_controla_permisos_cuenta_inactiva_y_autenticacion(self):
        self.usuario.rol.permisos.clear()
        self.assertEqual(self.registrar().status_code, 403)
        self.usuario.activo = False
        for ruta in ('movimientos/', 'resolver-movimiento/', 'ultimos-movimientos/'):
            self.assertEqual(self.client.get(ROOT + ruta).status_code, 403)
        self.assertEqual(self.registrar().status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.registrar().status_code, 401)
        self.assertEqual(self.client.get(ROOT + 'movimientos/').status_code, 401)

    def test_fallo_de_auditoria_revierte_stock_y_movimiento(self):
        with patch('apps.productos.views_movimientos.registrar_auditoria', side_effect=RuntimeError('fallo de prueba')):
            with self.assertLogs('django.request', level='ERROR'):
                with self.assertRaises(RuntimeError):
                    self.registrar()
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 10)
        self.assertFalse(Movimiento.objects.exists())


class HistorialMovimientosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = preparar_usuario()
        bodega = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        producto = Producto.objects.create(sku='HIST-055', nombre='Producto del historial')
        entrada = TipoMovimiento.objects.create(nombre='ENTRADA', operacion='+')
        salida = TipoMovimiento.objects.create(nombre='SALIDA', operacion='-')
        cls.ids = []
        ahora = timezone.now()
        for i in range(55):
            mov = Movimiento.objects.create(tipo=entrada if i % 2 == 0 else salida, bodega=bodega, usuario=cls.usuario, documento_referencia=f'Referencia {i}')
            Movimiento.objects.filter(pk=mov.pk).update(fecha_creacion=ahora + timedelta(minutes=i))
            cls.ids.append(DetalleMovimiento.objects.create(movimiento=mov, producto=producto, cantidad=i + 1).pk)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)

    def test_historial_completo_paginado_y_estable(self):
        ids = []
        for pagina, cantidad in ((1, 25), (2, 25), (3, 5)):
            respuesta = self.client.get(ROOT + 'movimientos/', {'page': pagina})
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.data['count'], 55)
            self.assertEqual(len(respuesta.data['results']), cantidad)
            ids.extend(mov['id'] for mov in respuesta.data['results'])
        self.assertEqual(ids, list(reversed(self.ids)))
        Movimiento.objects.all().update(fecha_creacion=timezone.now())
        self.assertEqual(self.client.get(ROOT + 'movimientos/').data['results'][0]['id'], self.ids[-1])

    def test_busqueda_tipo_y_pagina_se_aplican_a_todo_el_historial(self):
        respuesta = self.client.get(ROOT + 'movimientos/', {'search': 'HIST-055', 'tipo': 'ENTRADA', 'page': 2})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 28)
        self.assertEqual(len(respuesta.data['results']), 3)
        self.assertTrue(all(item['tipo'] == 'ENTRADA' for item in respuesta.data['results']))
        self.assertEqual(self.client.get(ROOT + 'movimientos/', {'search': 'inexistente'}).data['count'], 0)

    def test_fecha_filtra_por_dia_local_chileno_incluyendo_extremos(self):
        Movimiento.objects.all().update(fecha_creacion=datetime(2026, 10, 26, 2, 59, tzinfo=dt_timezone.utc))
        detalle = DetalleMovimiento.objects.get(pk=self.ids[0])
        Movimiento.objects.filter(pk=detalle.movimiento_id).update(fecha_creacion=datetime(2026, 10, 26, 3, 0, tzinfo=dt_timezone.utc))
        respuesta = self.client.get(ROOT + 'movimientos/', {'desde': '2026-10-26', 'hasta': '2026-10-26'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 1)
        self.assertEqual(respuesta.data['results'][0]['id'], self.ids[0])

    def test_rechaza_fechas_tipo_y_paginas_invalidas(self):
        for params in ({'desde': 'no-fecha'}, {'desde': '2026-10-28', 'hasta': '2026-10-27'}, {'tipo': 'OTRO'}):
            self.assertEqual(self.client.get(ROOT + 'movimientos/', params).status_code, 400)
        self.assertEqual(self.client.get(ROOT + 'movimientos/', {'page': 4}).status_code, 404)
        self.assertEqual(len(self.client.get(ROOT + 'movimientos/', {'page': 'last'}).data['results']), 5)

    def test_detalle_es_real_y_legacy_conserva_su_contrato(self):
        respuesta = self.client.get(ROOT + f'movimientos/{self.ids[-1]}/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['data']['documento_referencia'], 'Referencia 54')
        self.assertEqual(respuesta.data['data']['bodega'], 'Bodega Central')
        self.assertEqual(respuesta.data['data']['sku'], 'HIST-055')
        self.assertEqual(self.client.get(ROOT + 'movimientos/999999/').status_code, 404)
        legacy = self.client.get(ROOT + 'ultimos-movimientos/')
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(len(legacy.data['data']), 15)


class ConcurrenciaMovimientosTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_dos_salidas_simultaneas_no_generan_stock_negativo(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        usuario = preparar_usuario()
        bodega = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        producto = Producto.objects.create(sku='CONCURRENTE', nombre='Concurrente')
        stock = StockBodega.objects.create(producto=producto, bodega=bodega, cantidad_total=10)
        barrera = Barrier(2)

        def salida():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(Usuario.objects.get(pk=usuario.pk))
                barrera.wait(timeout=10)
                return client.post(ROOT + 'registrar-movimiento/', {
                    'producto_id': producto.pk, 'cantidad': 7, 'tipo_movimiento': 'SALIDA',
                }, format='json').status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            estados = sorted(pool.map(lambda _: salida(), range(2)))
        self.assertEqual(estados, [201, 409])
        stock.refresh_from_db()
        self.assertEqual(stock.cantidad_total, 3)
        self.assertEqual(Movimiento.objects.count(), 1)
