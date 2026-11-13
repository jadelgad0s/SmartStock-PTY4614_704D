"""Cálculos por bodega, mínimos, fechas de Chile y recorrido completo de alertas."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.usuarios.models import Permiso, Rol, Usuario
from .models import Bodega, DetalleMovimiento, Movimiento, Producto, StockBodega, StockMinimo, TipoMovimiento

ROOT = '/api/v1/productos/'
AHORA = datetime(2026, 10, 28, 2, 30, tzinfo=dt_timezone.utc)  # 27/10, 23:30 en Chile.


@override_settings(TIME_ZONE='America/Santiago')
class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol = Rol.objects.create(nombre='Administrador resumen', codigo='administrador')
        cls.rol.permisos.add(Permiso.objects.create(codigo='registrar_entrada', nombre='Entrada', modulo='movimientos'))
        cls.usuario = Usuario.objects.create_user(email='dashboard@example.com', nombres='Persona', apellidos='Prueba', rol=cls.rol)
        cls.central = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        cls.otra = Bodega.objects.create(nombre='Anexo', direccion='Anexo')
        cls.inactiva = Bodega.objects.create(nombre='Cerrada', direccion='Cerrada', activa=False)
        cls.productos = {}
        for sku, stock, minimo, activo in (
            ('SUF', 11, 5, True), ('BAJO', 3, 5, True), ('LIMITE', 5, 5, True),
            ('CERO', 0, 5, True), ('SIN', None, None, True), ('AGOTADO', 0, 0, True),
            ('DUP', 7, 9, True), ('INACTIVO', 99, 10, False),
        ):
            p = Producto.objects.create(sku=sku, nombre='Producto ' + sku, activo=activo)
            cls.productos[sku] = p
            if stock is not None: StockBodega.objects.create(producto=p, bodega=cls.central, cantidad_total=stock)
            if minimo is not None: StockMinimo.objects.create(producto=p, bodega=cls.central, cantidad_minima=minimo)
        StockBodega.objects.create(producto=cls.productos['SUF'], bodega=cls.otra, cantidad_total=100)
        StockBodega.objects.create(producto=cls.productos['SUF'], bodega=cls.inactiva, cantidad_total=1000)
        cls.entrada = TipoMovimiento.objects.create(nombre='ENTRADA', operacion='+')
        cls.salida = TipoMovimiento.objects.create(nombre='SALIDA', operacion='-')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)

    def resumen(self, **params):
        with patch('apps.productos.views_dashboard.timezone.now', return_value=AHORA):
            respuesta = self.client.get(ROOT + 'dashboard-resumen/', params)
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        return respuesta.data['data']

    def movimiento(self, fecha, cantidad, entrada=True, bodega=None, producto=None):
        mov = Movimiento.objects.create(tipo=self.entrada if entrada else self.salida, bodega=bodega or self.central, usuario=self.usuario)
        Movimiento.objects.filter(pk=mov.pk).update(fecha_creacion=fecha)
        return DetalleMovimiento.objects.create(movimiento=mov, producto=producto or self.productos['SUF'], cantidad=cantidad)

    def test_estados_cuentan_productos_y_stock_suma_solo_la_bodega_y_activos(self):
        datos = self.resumen()
        self.assertEqual(datos['bodega']['id'], self.central.pk)
        self.assertEqual(datos['kpi_stock'], 26)
        self.assertEqual(datos['estado_inventario'], {'total': 7, 'suficiente': 1, 'bajo': 3, 'agotado': 3})
        self.assertEqual(datos['kpi_alertas'], 3)
        self.assertEqual(datos['kpi_bajo'], 3)
        self.assertNotIn(self.inactiva.pk, [b['id'] for b in datos['bodegas']])

    def test_bodega_seleccionada_no_mezcla_stock_ni_movimientos(self):
        self.movimiento(AHORA, 4)
        self.movimiento(AHORA, 20, bodega=self.otra)
        datos = self.resumen(bodega=self.otra.pk)
        self.assertEqual(datos['kpi_stock'], 100)
        self.assertEqual(datos['kpi_entradas'], 20)
        self.assertEqual(datos['estado_inventario']['suficiente'], 1)
        self.assertEqual(len(datos['recientes']), 1)
        self.assertEqual(datos['recientes'][0]['bodega'], 'Anexo')

    def test_sin_fila_stock_es_agotado_y_cada_producto_se_cuenta_una_vez(self):
        r = self.client.get(ROOT + 'dashboard-alertas/', {'estado': 'agotado', 'search': 'SIN'})
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['stock'], 0)
        r = self.client.get(ROOT + 'dashboard-alertas/', {'search': 'DUP'})
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['stock'], 7)
        self.assertEqual(r.data['results'][0]['minimo'], 9)

    def test_minimo_igual_stock_es_bajo_y_sin_minimo_positivo_es_suficiente(self):
        StockMinimo.objects.filter(producto=self.productos['SUF']).delete()
        datos = self.resumen()
        self.assertEqual(datos['estado_inventario']['suficiente'], 1)
        r = self.client.get(ROOT + 'dashboard-alertas/', {'search': 'LIMITE', 'estado': 'bajo'})
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['estado'], 'bajo')

    def test_hoy_y_series_usan_dia_chileno_y_suman_unidades_no_operaciones(self):
        self.movimiento(datetime(2026, 10, 27, 2, 59, tzinfo=dt_timezone.utc), 7)  # 26/10
        self.movimiento(datetime(2026, 10, 27, 3, 0, tzinfo=dt_timezone.utc), 12)
        self.movimiento(AHORA, 5)
        self.movimiento(AHORA, 2, entrada=False)
        self.movimiento(datetime(2026, 10, 28, 3, 0, tzinfo=dt_timezone.utc), 99)  # 28/10
        datos = self.resumen()
        self.assertEqual(datos['kpi_entradas'], 17)
        self.assertEqual(datos['kpi_salidas'], 2)
        self.assertEqual(datos['chart_entradas'][-2:], [7, 17])
        self.assertEqual(datos['chart_salidas'][-1], 2)
        self.assertEqual(datos['chart_fechas'][-1], '2026-10-27')
        self.assertEqual(datos['zona_horaria'], 'America/Santiago')
        self.assertEqual(datos['actualizado'], '2026-10-27T23:30:00-03:00')

    def test_7_y_30_dias_incluyen_extremos_y_rellenan_dias_sin_actividad(self):
        self.movimiento(datetime(2026, 9, 28, 3, tzinfo=dt_timezone.utc), 20)
        self.movimiento(datetime(2026, 9, 27, 23, tzinfo=dt_timezone.utc), 99)
        self.movimiento(datetime(2026, 10, 21, 3, tzinfo=dt_timezone.utc), 4)
        semana = self.resumen()
        mes = self.resumen(dias='30')
        self.assertEqual(semana['chart_fechas'][0], '2026-10-21')
        self.assertEqual(semana['chart_entradas'][0], 4)
        self.assertEqual(len(mes['chart_entradas']), 30)
        self.assertEqual(mes['chart_fechas'][0], '2026-09-28')
        self.assertEqual(mes['chart_entradas'][0], 20)
        self.assertEqual(sum(mes['chart_entradas']), 24)
        self.assertEqual(mes['chart_entradas'][-1], 0)

    def test_cambio_horario_chile_conserva_fechas_locales(self):
        zona = ZoneInfo('America/Santiago')
        self.movimiento(datetime(2026, 9, 5, 23, 59, tzinfo=zona), 2)
        self.movimiento(datetime(2026, 9, 6, 1, 0, tzinfo=zona), 3)
        self.movimiento(datetime(2026, 9, 7, 0, 0, tzinfo=zona), 9)
        with patch('apps.productos.views_dashboard.timezone.now', return_value=datetime(2026, 9, 6, 18, tzinfo=zona)):
            datos = self.client.get(ROOT + 'dashboard-resumen/').data['data']
        self.assertEqual(datos['chart_entradas'][-2:], [2, 3])
        self.assertEqual(datos['kpi_entradas'], 3)

    def test_recientes_tienen_fecha_tipo_operador_y_desempate_por_id(self):
        for i in range(7): self.movimiento(AHORA - timedelta(days=10), i + 1, entrada=i % 2 == 0)
        datos = self.resumen()
        recientes = datos['recientes']
        self.assertEqual(len(recientes), 5)
        self.assertEqual([r['id'] for r in recientes], list(DetalleMovimiento.objects.order_by('-id').values_list('id', flat=True)[:5]))
        self.assertEqual(recientes[0]['cantidad'], 7)
        self.assertEqual(recientes[1]['tipo'], 'SALIDA')
        self.assertEqual(recientes[0]['usuario'], 'Persona Prueba')
        self.assertTrue(recientes[0]['fecha_iso'])
        self.assertTrue(recientes[0]['id_trx'].startswith('#TRX-'))
        self.assertEqual(sum(datos['chart_entradas']), 0)

    def test_recientes_conservan_historia_de_producto_desactivado(self):
        self.movimiento(AHORA, 2, producto=self.productos['INACTIVO'])
        datos = self.resumen()
        self.assertEqual(datos['kpi_entradas'], 2)
        self.assertEqual(datos['recientes'][0]['sku'], 'INACTIVO')
        self.assertEqual(datos['kpi_stock'], 26)

    def test_alertas_completas_paginadas_y_filtradas_por_nombre_sku_y_estado(self):
        Producto.objects.bulk_create([Producto(sku=f'PAG-{i:03}', nombre=f'Producto paginado {i:03}') for i in range(55)])
        parametros = {'search': 'paginado', 'estado': 'agotado', 'bodega': self.central.pk}
        ids = []
        for pagina, cantidad in ((1, 25), (2, 25), (3, 5)):
            r = self.client.get(ROOT + 'dashboard-alertas/', {**parametros, 'page': pagina})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data['count'], 55)
            self.assertEqual(len(r.data['results']), cantidad)
            ids += [p['producto_id'] for p in r.data['results']]
        self.assertEqual(len(set(ids)), 55)
        r = self.client.get(ROOT + 'dashboard-alertas/', {'search': 'PAG-054'})
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['sku'], 'PAG-054')
        self.assertEqual(self.client.get(ROOT + 'dashboard-alertas/', {**parametros, 'page': 'last'}).data['results'][0]['sku'], 'PAG-050')

    def test_resumen_limita_cinco_alertas_pero_no_el_contador(self):
        datos = self.resumen()
        self.assertEqual(len(datos['alertas']), 5)
        self.assertEqual(datos['kpi_alertas'] + datos['kpi_bajo'], 6)
        self.assertTrue(all(a['estado'] == 'agotado' for a in datos['alertas'][:3]))
        self.assertNotIn('INACTIVO', [a['sku'] for a in datos['alertas']])
        self.assertTrue(all(a['bodega_id'] == self.central.pk for a in datos['alertas']))

    def test_validacion_de_bodega_periodo_filtros_y_paginas(self):
        for datos in ({'dias': '6'}, {'dias': '999'}, {'bodega': 'no'}, {'bodega': self.inactiva.pk}, {'bodega': 99999}, {'search': 'x' * 201}, {'estado': 'otra'}):
            with self.subTest(datos=datos):
                self.assertEqual(self.client.get(ROOT + 'dashboard-resumen/', datos).status_code, 400)
        for page in ('x', '0', '-1', '999'):
            self.assertEqual(self.client.get(ROOT + 'dashboard-alertas/', {'page': page}).status_code, 404)

    def test_sin_productos_no_inventa_una_categoria_saludable(self):
        Producto.objects.update(activo=False)
        datos = self.resumen()
        self.assertEqual(datos['estado_inventario'], {'total': 0, 'suficiente': 0, 'bajo': 0, 'agotado': 0})
        self.assertEqual(datos['kpi_stock'], 0)
        self.assertEqual(datos['alertas'], [])

    def test_sin_bodegas_activas_muestra_vacio_y_no_consulta_stock_archivado(self):
        Bodega.objects.update(activa=False)
        datos = self.resumen()
        self.assertIsNone(datos['bodega'])
        self.assertEqual(datos['bodegas'], [])
        self.assertEqual(datos['kpi_stock'], 0)
        self.assertEqual(datos['estado_inventario']['total'], 0)
        self.assertEqual(self.client.get(ROOT + 'dashboard-alertas/').status_code, 400)

    def test_default_usa_primera_bodega_activa_si_no_existe_central(self):
        Bodega.objects.filter(pk=self.central.pk).update(activa=False)
        self.assertEqual(self.resumen()['bodega']['id'], self.otra.pk)

    def test_capacidades_reflejan_permisos_de_registro_y_administracion(self):
        self.assertEqual(self.resumen()['permisos'], {'registrar_movimiento': True, 'usuarios': True, 'auditoria': True, 'configuracion': False})
        self.rol.permisos.clear()
        self.assertFalse(self.resumen()['permisos']['registrar_movimiento'])
        self.usuario.is_superuser = True
        self.usuario.is_staff = True
        p = self.resumen()['permisos']
        self.assertTrue(all(p.values()))

    def test_solo_lectura_cuenta_activa_y_autenticada_sin_cache(self):
        for ruta in ('dashboard-resumen/', 'dashboard-alertas/'):
            self.assertIn('no-store', self.client.get(ROOT + ruta)['Cache-Control'])
            self.assertEqual(self.client.post(ROOT + ruta, {}, format='json').status_code, 405)
            self.usuario.activo = False
            self.assertEqual(self.client.get(ROOT + ruta).status_code, 403)
            self.usuario.activo = True
            self.client.force_authenticate(None)
            self.assertEqual(self.client.get(ROOT + ruta).status_code, 401)
            self.client.force_authenticate(self.usuario)
        self.usuario.is_superuser = True
        for ruta in ('dashboard-resumen/', 'dashboard-alertas/'):
            self.assertEqual(self.client.post(ROOT + ruta, {}, format='json').status_code, 405)

    def test_numero_consultas_del_historico_no_crece_de_7_a_30_dias(self):
        with CaptureQueriesContext(connection) as semana: self.resumen(dias='7')
        with CaptureQueriesContext(connection) as mes: self.resumen(dias='30')
        self.assertLessEqual(len(semana), 9)
        self.assertEqual(len(semana), len(mes))
