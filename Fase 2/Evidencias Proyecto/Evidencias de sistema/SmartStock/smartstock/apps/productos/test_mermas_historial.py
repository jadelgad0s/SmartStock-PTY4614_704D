"""Historial completo y selección de productos con stock de Bodega Central."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone as dt_timezone
from threading import Barrier
from unittest.mock import patch

from django.db import connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from apps.usuarios.models import Permiso, Rol, Usuario
from .models import Bodega, CodigoBarra, Merma, MotivoMerma, Movimiento, Producto, StockBodega

ROOT = '/api/v1/productos/mermas/'


class HistorialMermasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_superuser(
            email='historial-mermas@example.com', password='PasswordSeguro123!', nombres='Persona', apellidos='Prueba',
        )
        cls.bodega = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        cls.otra = Bodega.objects.create(nombre='Otra bodega', direccion='Otra')
        cls.producto = Producto.objects.create(sku='HIST-055', nombre='Producto del historial')
        cls.stock = StockBodega.objects.create(producto=cls.producto, bodega=cls.bodega, cantidad_total=10)
        StockBodega.objects.create(producto=cls.producto, bodega=cls.otra, cantidad_total=90)
        cls.motivo = MotivoMerma.objects.create(descripcion='Daño en Bodega')
        vencido = MotivoMerma.objects.create(descripcion='Producto Vencido')
        cls.ids = []
        for i in range(55):
            merma = Merma.objects.create(
                producto=cls.producto, bodega=cls.bodega, motivo=cls.motivo if i % 2 == 0 else vencido,
                usuario=cls.usuario, cantidad=1, observacion=f'Observación completa {i}.\nSegunda línea.',
            )
            cls.ids.append(merma.pk)
        # Fechas iguales fuerzan el desempate por ID entre páginas.
        Merma.objects.all().update(fecha_creacion=timezone.now())

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)

    def test_25_por_pagina_y_todos_los_registros_en_orden_estable(self):
        ids = []
        for pagina, cantidad in ((1, 25), (2, 25), (3, 5)):
            respuesta = self.client.get(ROOT + 'historial/', {'page': pagina, 'page_size': 100})
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.data['count'], 55)
            self.assertEqual(len(respuesta.data['results']), cantidad)
            ids.extend(item['id'] for item in respuesta.data['results'])
        self.assertEqual(ids, list(reversed(self.ids)))

    def test_busqueda_y_motivo_se_aplican_antes_de_paginar(self):
        respuesta = self.client.get(ROOT + 'historial/', {'search': 'HIST-055', 'motivo': 'DAÑO', 'page': 2})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 28)
        self.assertEqual(len(respuesta.data['results']), 3)
        self.assertTrue(all(item['motivo_codigo'] == 'DAÑO' for item in respuesta.data['results']))
        self.assertEqual(self.client.get(ROOT + 'historial/', {'search': 'inexistente'}).data['count'], 0)

    def test_fechas_inclusivas_usan_el_dia_local_chileno(self):
        Merma.objects.all().update(fecha_creacion=datetime(2026, 10, 26, 2, 59, tzinfo=dt_timezone.utc))
        Merma.objects.filter(pk=self.ids[0]).update(fecha_creacion=datetime(2026, 10, 26, 3, 0, tzinfo=dt_timezone.utc))
        respuesta = self.client.get(ROOT + 'historial/', {'desde': '2026-10-26', 'hasta': '2026-10-26'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 1)
        self.assertEqual(respuesta.data['results'][0]['id'], self.ids[0])

    def test_rechaza_filtros_y_paginas_invalidas(self):
        for parametros in ({'desde': 'x'}, {'motivo': 'OTRO'}, {'desde': '2026-10-28', 'hasta': '2026-10-27'}):
            self.assertEqual(self.client.get(ROOT + 'historial/', parametros).status_code, 400)
        self.assertEqual(self.client.get(ROOT + 'historial/', {'page': 4}).status_code, 404)
        self.assertEqual(len(self.client.get(ROOT + 'historial/', {'page': 'last'}).data['results']), 5)

    def test_detalle_conserva_observacion_completa_y_estado(self):
        respuesta = self.client.get(ROOT + str(self.ids[-1]) + '/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['data']['observacion'], 'Observación completa 54.\nSegunda línea.')
        self.assertEqual(respuesta.data['data']['estado'], 'Registrada')
        self.assertEqual(respuesta.data['data']['bodega'], 'Bodega Central')
        self.assertEqual(self.client.get(ROOT + '999999/').status_code, 404)

    def test_legacy_conserva_su_formato_y_limite(self):
        respuesta = self.client.get(ROOT)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data['success'])
        self.assertEqual(len(respuesta.data['data']), 50)

    def test_catalogo_completo_de_productos_y_stock_de_bodega_central(self):
        Producto.objects.bulk_create([Producto(sku=f'AAA-{i:03d}', nombre=f'A producto {i:03d}') for i in range(55)])
        CodigoBarra.objects.create(producto=self.producto, codigo='CODIGO-UNO')
        CodigoBarra.objects.create(producto=self.producto, codigo='CODIGO-DOS')
        ids = []
        for pagina, cantidad in ((1, 25), (2, 25), (3, 6)):
            respuesta = self.client.get(ROOT + 'productos/', {'page': pagina})
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.data['count'], 56)
            self.assertEqual(len(respuesta.data['results']), cantidad)
            ids.extend(item['id'] for item in respuesta.data['results'])
        self.assertEqual(len(set(ids)), 56)
        respuesta = self.client.get(ROOT + 'productos/', {'search': 'CODIGO-'})
        self.assertEqual(respuesta.data['count'], 1)
        self.assertEqual(respuesta.data['results'][0]['stock_disponible'], 10)
        self.assertEqual(respuesta.data['results'][0]['bodega'], 'Bodega Central')

    def test_catalogo_excluye_inactivos_y_cero_stock_si_central_inactiva(self):
        Producto.objects.filter(pk=self.producto.pk).update(activo=False)
        self.assertEqual(self.client.get(ROOT + 'productos/').data['count'], 0)
        Producto.objects.filter(pk=self.producto.pk).update(activo=True)
        Bodega.objects.filter(pk=self.bodega.pk).update(activa=False)
        self.assertEqual(self.client.get(ROOT + 'productos/').data['results'][0]['stock_disponible'], 0)

    def test_permisos_en_todos_los_nuevos_endpoints(self):
        rutas = ('historial/', 'productos/', str(self.ids[0]) + '/')
        self.client.force_authenticate(None)
        for ruta in rutas:
            self.assertEqual(self.client.get(ROOT + ruta).status_code, 401)
        usuario = Usuario.objects.create_user(email='sin-permiso@example.com', password='Password123!', nombres='Sin', apellidos='Permiso')
        self.client.force_authenticate(usuario)
        for ruta in rutas:
            self.assertEqual(self.client.get(ROOT + ruta).status_code, 403)
        self.usuario.activo = False
        self.client.force_authenticate(self.usuario)
        for ruta in rutas:
            self.assertEqual(self.client.get(ROOT + ruta).status_code, 403)

    def test_rechazo_por_stock_informa_disponible_y_no_modifica_registros(self):
        respuesta = self.client.post(ROOT, {'producto_id': self.producto.pk, 'cantidad': 11, 'motivo': 'DAÑO', 'observacion': 'Daño comprobado'}, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data['errores']['stock_disponible'], 10)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 10)
        self.assertEqual(Merma.objects.count(), 55)

    def test_error_de_auditoria_revierte_tambien_el_descuento(self):
        with patch('apps.productos.views_mermas.registrar_auditoria', side_effect=RuntimeError('fallo de prueba')):
            with self.assertLogs('django.request', level='ERROR'):
                with self.assertRaises(RuntimeError):
                    self.client.post(ROOT, {'producto_id': self.producto.pk, 'cantidad': 3, 'motivo': 'DAÑO', 'observacion': 'Daño comprobado'}, format='json')
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 10)
        self.assertEqual(Merma.objects.count(), 55)


class ConcurrenciaMermaMovimientoTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_merma_y_salida_simultaneas_comparten_el_mismo_stock(self):
        rol = Rol.objects.create(nombre='Encargado', codigo='encargado_bodega')
        for codigo in ('registrar_merma', 'registrar_salida'):
            rol.permisos.add(Permiso.objects.create(codigo=codigo, nombre=codigo, modulo='movimientos'))
        usuario = Usuario.objects.create_user(email='concurrente-merma@example.com', password='Password123!', nombres='Persona', apellidos='Prueba', rol=rol)
        bodega = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        producto = Producto.objects.create(sku='MIXTO', nombre='Stock compartido')
        stock = StockBodega.objects.create(producto=producto, bodega=bodega, cantidad_total=10)
        barrera = Barrier(2)

        def registrar(es_merma):
            try:
                client = APIClient()
                client.force_authenticate(Usuario.objects.get(pk=usuario.pk))
                payload = {'producto_id': producto.pk, 'cantidad': 7}
                if es_merma:
                    payload.update(motivo='DAÑO', observacion='Daño comprobado')
                    url = ROOT
                else:
                    payload['tipo_movimiento'] = 'SALIDA'
                    url = '/api/v1/productos/registrar-movimiento/'
                barrera.wait(timeout=10)
                return client.post(url, payload, format='json').status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(registrar, (True, False)))
        self.assertEqual(resultados.count(201), 1)
        self.assertTrue(all(estado in (201, 400, 409) for estado in resultados))
        stock.refresh_from_db()
        self.assertEqual(stock.cantidad_total, 3)
        self.assertEqual(Merma.objects.count() + Movimiento.objects.count(), 1)
