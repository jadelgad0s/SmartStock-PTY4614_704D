"""Invariantes de almacenamiento y operaciones simultáneas sobre stock único."""
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError, close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.test import APIClient

from apps.usuarios.models import Permiso, Rol, Usuario
from .models import (Bodega, DetalleMovimiento, DetalleTransferencia, Merma, MotivoMerma,
                     Movimiento, Producto, StockBodega, StockMinimo, TipoMovimiento, Transferencia)

MAX = 2147483647


class RestriccionesStockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user(email='restricciones@example.com')
        cls.producto = Producto.objects.create(sku='RESTRICCION', nombre='Producto de prueba')
        cls.bodega = Bodega.objects.create(nombre='Central')
        cls.otra = Bodega.objects.create(nombre='Otra')
        cls.stock = StockBodega.objects.create(producto=cls.producto, bodega=cls.bodega, cantidad_total=10)
        cls.minimo = StockMinimo.objects.create(producto=cls.producto, bodega=cls.bodega, cantidad_minima=5)
        tipo = TipoMovimiento.objects.create(nombre='ENTRADA', operacion='+')
        mov = Movimiento.objects.create(tipo=tipo, bodega=cls.bodega, usuario=cls.usuario)
        cls.detalle = DetalleMovimiento.objects.create(movimiento=mov, producto=cls.producto, cantidad=1)
        tr = Transferencia.objects.create(bodega_origen=cls.bodega, bodega_destino=cls.otra, usuario=cls.usuario, estado='COMPLETADA')
        cls.detalle_tr = DetalleTransferencia.objects.create(transferencia=tr, producto=cls.producto, cantidad=1)
        motivo = MotivoMerma.objects.create(descripcion='Prueba')
        cls.merma = Merma.objects.create(producto=cls.producto, bodega=cls.bodega, usuario=cls.usuario, motivo=motivo, cantidad=1)

    def test_no_se_puede_duplicar_stock_o_minimo_sin_validacion_de_formulario(self):
        for modelo in (StockBodega, StockMinimo):
            with self.subTest(modelo=modelo.__name__), self.assertRaises(IntegrityError), transaction.atomic():
                modelo.objects.create(producto=self.producto, bodega=self.bodega)
            modelo.objects.create(producto=self.producto, bodega=self.otra)
        self.assertEqual(StockBodega.objects.count(), 2)
        self.assertEqual(StockMinimo.objects.count(), 2)

    def test_update_directo_rechaza_negativos_y_desbordes(self):
        for fila, campo in ((self.stock, 'cantidad_total'), (self.minimo, 'cantidad_minima')):
            for valor in (-1, MAX + 1):
                with self.subTest(modelo=type(fila).__name__, valor=valor), self.assertRaises(DatabaseError), transaction.atomic():
                    type(fila).objects.filter(pk=fila.pk).update(**{campo: valor})
            fila.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 10)
        self.assertEqual(self.minimo.cantidad_minima, 5)

    def test_cero_es_valido_para_stock_y_minimo_y_no_para_operaciones(self):
        StockBodega.objects.filter(pk=self.stock.pk).update(cantidad_total=0)
        StockMinimo.objects.filter(pk=self.minimo.pk).update(cantidad_minima=0)
        for fila in (self.detalle, self.detalle_tr, self.merma):
            for valor in (0, -1, MAX + 1):
                with self.subTest(modelo=type(fila).__name__, valor=valor), self.assertRaises(DatabaseError), transaction.atomic():
                    type(fila).objects.filter(pk=fila.pk).update(cantidad=valor)
            fila.refresh_from_db()
            self.assertEqual(fila.cantidad, 1)

    def test_limites_validos_se_guardan(self):
        for fila, campo in ((self.stock, 'cantidad_total'), (self.minimo, 'cantidad_minima'),
                            (self.detalle, 'cantidad'), (self.detalle_tr, 'cantidad'), (self.merma, 'cantidad')):
            type(fila).objects.filter(pk=fila.pk).update(**{campo: MAX})
            fila.refresh_from_db()
            self.assertEqual(getattr(fila, campo), MAX)

    def test_modelos_validan_cantidades_antes_de_guardar(self):
        for fila, campo, valor in ((self.stock, 'cantidad_total', -1), (self.minimo, 'cantidad_minima', MAX + 1),
                                   (self.detalle, 'cantidad', 0), (self.detalle_tr, 'cantidad', -1), (self.merma, 'cantidad', 0)):
            with self.subTest(modelo=type(fila).__name__), self.assertRaises(ValidationError):
                setattr(fila, campo, valor)
                fila.full_clean(exclude=[f.name for f in fila._meta.fields if f.name != campo], validate_unique=False, validate_constraints=False)

    def test_sql_directo_tampoco_puede_descontar_mas_que_el_saldo(self):
        from django.db import connection
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('UPDATE stock_bodega SET cantidad_total = cantidad_total - 11 WHERE id = %s', [self.stock.pk])
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 10)

    def test_diagnostico_posterior_no_modifica_inventario(self):
        salida = StringIO()
        antes = list(StockBodega.objects.values())
        call_command('revisar_integridad_stock', stdout=salida)
        self.assertIn('sin duplicados', salida.getvalue())
        self.assertEqual(list(StockBodega.objects.values()), antes)


@override_settings(SMS_ALERTAS_ACTIVAS=False)
class ConcurrenciaIntegridadTests(TransactionTestCase):
    def setUp(self):
        rol = Rol.objects.create(codigo='operador', nombre='Operador integridad')
        for codigo in ('registrar_entrada', 'editar_producto'):
            rol.permisos.add(Permiso.objects.create(codigo=codigo, nombre=codigo, modulo='inventario'))
        self.usuario = Usuario.objects.create_user(email='concurrencia-integridad@example.com', rol=rol)
        self.bodega = Bodega.objects.create(nombre='Bodega Central')
        self.producto = Producto.objects.create(sku='INTEGRIDAD-CONC', nombre='Concurrente')

    def simultaneos(self, operacion):
        barrera = Barrier(2)
        def ejecutar(i):
            close_old_connections()
            try:
                persona = Usuario.objects.select_related('rol').get(pk=self.usuario.pk)
                client = APIClient(); client.force_authenticate(persona)
                barrera.wait(timeout=10)
                return operacion(client, i)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(ejecutar, range(2)))

    @skipUnlessDBFeature('has_select_for_update')
    def test_primera_entrada_simultanea_crea_una_fila_y_conserva_ambas_operaciones(self):
        def entrada(client, _):
            return client.post('/api/v1/productos/registrar-movimiento/', {
                'bodega_id': self.bodega.pk, 'producto_id': self.producto.pk,
                'tipo_movimiento': 'ENTRADA', 'cantidad': 5,
            }, format='json').status_code
        self.assertEqual(sorted(self.simultaneos(entrada)), [201, 201])
        self.assertEqual(StockBodega.objects.get(producto=self.producto, bodega=self.bodega).cantidad_total, 10)
        self.assertEqual(DetalleMovimiento.objects.count(), 2)

    @skipUnlessDBFeature('has_select_for_update')
    def test_primer_minimo_simultaneo_se_guarda_una_sola_vez(self):
        def minimo(client, i):
            return client.patch(f'/api/v1/productos/{self.producto.pk}/stock-minimo/', {
                'bodega': self.bodega.pk, 'cantidad_minima': i + 2,
            }, format='json').status_code
        self.assertEqual(sorted(self.simultaneos(minimo)), [200, 200])
        self.assertIn(StockMinimo.objects.get(producto=self.producto, bodega=self.bodega).cantidad_minima, (2, 3))

    @skipUnlessDBFeature('has_select_for_update')
    def test_dos_inserciones_fuera_de_la_api_no_pueden_duplicar_la_pareja(self):
        def alta(_client, _i):
            try:
                with transaction.atomic():
                    StockBodega.objects.create(producto_id=self.producto.pk, bodega_id=self.bodega.pk, cantidad_total=5)
                return 'creado'
            except IntegrityError:
                return 'duplicado'
        self.assertEqual(sorted(self.simultaneos(alta)), ['creado', 'duplicado'])
        self.assertEqual(StockBodega.objects.get().cantidad_total, 5)
