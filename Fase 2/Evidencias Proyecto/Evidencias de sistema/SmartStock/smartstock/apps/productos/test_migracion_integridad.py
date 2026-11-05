"""Migración real desde datos heredados y rechazo atómico de datos ambiguos."""
from importlib import import_module
from io import StringIO

from django.core.management import call_command, CommandError
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from apps.core.models import Auditoria

ANTERIOR = [('productos', '0006_cupoconsultaexterna_fichaproductoexterna_and_more')]
NUEVA = [('productos', '0007_integridad_stock')]


class MigracionIntegridadTests(TransactionTestCase):
    def setUp(self):
        ejecutor = MigrationExecutor(connection)
        self.ultimas = ejecutor.loader.graph.leaf_nodes()
        ejecutor.migrate(ANTERIOR)
        self.apps = ejecutor.loader.project_state(ANTERIOR).apps
        self.Stock = self.apps.get_model('productos', 'StockBodega')
        self.Minimo = self.apps.get_model('productos', 'StockMinimo')
        self.p = self.apps.get_model('productos', 'Producto').objects.create(sku='LEGACY', nombre='Producto heredado', activo=False)
        self.b = self.apps.get_model('productos', 'Bodega').objects.create(nombre='Bodega anterior', activa=False)
        self.otra = self.apps.get_model('productos', 'Bodega').objects.create(nombre='Otra')

    def tearDown(self):
        # Incluso una migración rechazada debe dejar el esquema listo para la suite.
        for nombre in ('DetalleMovimiento', 'DetalleTransferencia', 'Merma', 'StockBodega', 'StockMinimo'):
            self.apps.get_model('productos', nombre).objects.all().delete()
        MigrationExecutor(connection).migrate(self.ultimas)
        super().tearDown()

    def migrar(self):
        MigrationExecutor(connection).migrate(NUEVA)

    def test_consolida_conservando_total_minimo_mas_alto_y_otras_bodegas(self):
        primero = self.Stock.objects.create(producto=self.p, bodega=self.b, cantidad_total=10)
        self.Stock.objects.create(producto=self.p, bodega=self.b, cantidad_total=14)
        self.Stock.objects.create(producto=self.p, bodega=self.otra, cantidad_total=6)
        self.Minimo.objects.create(producto=self.p, bodega=self.b, cantidad_minima=2)
        self.Minimo.objects.create(producto=self.p, bodega=self.b, cantidad_minima=9)
        self.migrar()
        self.assertEqual(list(self.Stock.objects.order_by('bodega_id').values_list('cantidad_total', flat=True)), [24, 6])
        self.assertEqual(self.Stock.objects.get(bodega=self.b).pk, primero.pk)
        self.assertEqual(self.Minimo.objects.get().cantidad_minima, 9)
        for nombre in ('Movimiento', 'Merma', 'Notificacion', 'EnvioAlertaSMS'):
            self.assertEqual(self.apps.get_model('productos', nombre).objects.count(), 0)
        self.assertEqual(Auditoria.objects.count(), 0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.Stock.objects.create(producto=self.p, bodega=self.b, cantidad_total=1)

    def test_no_oculta_negativos_al_sumar_y_no_consolida_parcialmente(self):
        self.Stock.objects.create(producto=self.p, bodega=self.b, cantidad_total=10)
        self.Stock.objects.create(producto=self.p, bodega=self.b, cantidad_total=2)
        malo = self.Stock.objects.create(producto=self.p, bodega=self.otra, cantidad_total=-1)
        with self.assertRaisesRegex(RuntimeError, 'StockBodega.cantidad_total'):
            self.migrar()
        self.assertEqual(list(self.Stock.objects.order_by('pk').values_list('cantidad_total', flat=True)), [10, 2, -1])
        self.assertFalse(MigrationExecutor(connection).loader.applied_migrations.get(('productos', '0007_integridad_stock')))
        malo.cantidad_total = 0; malo.save()
        self.migrar()
        self.assertEqual(self.Stock.objects.get(bodega=self.b).cantidad_total, 12)

    def test_rechaza_suma_mayor_al_rango_sin_recortar_unidades(self):
        self.Stock.objects.create(producto=self.p, bodega=self.b, cantidad_total=2147483647)
        self.Stock.objects.create(producto=self.p, bodega=self.b, cantidad_total=1)
        with self.assertRaisesRegex(RuntimeError, '2147483648'):
            self.migrar()
        self.assertEqual(self.Stock.objects.count(), 2)

    def test_rechaza_minimo_negativo_sin_elegir_otro_silenciosamente(self):
        self.Minimo.objects.create(producto=self.p, bodega=self.b, cantidad_minima=-1)
        self.Minimo.objects.create(producto=self.p, bodega=self.b, cantidad_minima=5)
        with self.assertRaisesRegex(RuntimeError, 'StockMinimo.cantidad_minima'):
            self.migrar()
        self.assertEqual(self.Minimo.objects.count(), 2)

    def test_detalles_y_mermas_de_cero_o_negativos_requieren_revision(self):
        u = self.apps.get_model('usuarios', 'Usuario').objects.create(email='migracion@example.com')
        tipo = self.apps.get_model('productos', 'TipoMovimiento').objects.create(nombre='ENTRADA', operacion='+')
        mov = self.apps.get_model('productos', 'Movimiento').objects.create(tipo=tipo, bodega=self.b, usuario=u)
        self.apps.get_model('productos', 'DetalleMovimiento').objects.create(movimiento=mov, producto=self.p, cantidad=0)
        tr = self.apps.get_model('productos', 'Transferencia').objects.create(bodega_origen=self.b, bodega_destino=self.otra, usuario=u, estado='COMPLETADA')
        self.apps.get_model('productos', 'DetalleTransferencia').objects.create(transferencia=tr, producto=self.p, cantidad=-1)
        motivo = self.apps.get_model('productos', 'MotivoMerma').objects.create(descripcion='Prueba')
        self.apps.get_model('productos', 'Merma').objects.create(producto=self.p, bodega=self.b, usuario=u, motivo=motivo, cantidad=0)
        with self.assertRaises(RuntimeError) as e:
            self.migrar()
        for nombre in ('DetalleMovimiento', 'DetalleTransferencia', 'Merma'):
            self.assertIn(nombre, str(e.exception))

    def test_diagnostico_anterior_detecta_grupos_sin_modificar_filas(self):
        for cantidad in (3, 4): self.Stock.objects.create(producto=self.p, bodega=self.b, cantidad_total=cantidad)
        salida = StringIO()
        call_command('revisar_integridad_stock', stdout=salida)
        self.assertIn('stock duplicado: 1', salida.getvalue())
        self.assertEqual(self.Stock.objects.count(), 2)
        self.Stock.objects.create(producto=self.p, bodega=self.otra, cantidad_total=-1)
        with self.assertRaises(CommandError):
            call_command('revisar_integridad_stock', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(self.Stock.objects.count(), 3)

    def test_mas_de_un_lote_de_grupos_se_consolida_completo(self):
        productos = self.apps.get_model('productos', 'Producto').objects.bulk_create([
            self.apps.get_model('productos', 'Producto')(sku=f'LOTE-{n}', nombre=f'Lote {n}') for n in range(205)
        ])
        self.Stock.objects.bulk_create([self.Stock(producto=p, bodega=self.b, cantidad_total=n) for p in productos for n in (2, 3)])
        self.migrar()
        self.assertEqual(self.Stock.objects.count(), 205)
        self.assertEqual(set(self.Stock.objects.values_list('cantidad_total', flat=True)), {5})
