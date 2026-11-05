"""Reportes completos y conciliación del Kardex con movimientos, mermas y stock."""
import csv
import io
from datetime import datetime, timedelta, timezone as tz
from unittest.mock import patch

from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.usuarios.models import Permiso, Rol, Usuario
from .models import (Bodega, Producto, StockBodega, StockMinimo, TipoMovimiento,
                     Movimiento, DetalleMovimiento, MotivoMerma, Merma, Transferencia, DetalleTransferencia)
from .reportes import PlanReporte, ZONA

ROOT = '/api/v1/reportes/'


class ReportesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ver = Permiso.objects.create(codigo='ver_reportes', nombre='Ver reportes', modulo='reportes')
        exportar = Permiso.objects.create(codigo='exportar_reportes', nombre='Exportar reportes', modulo='reportes')
        rol = Rol.objects.create(codigo='administrador', nombre='Administrador')
        rol.permisos.add(ver, exportar)
        cls.admin = Usuario.objects.create_user(email='reportes@example.com', nombres='Persona', apellidos='Prueba', rol=rol)
        lector = Rol.objects.create(codigo='encargado_bodega', nombre='Encargado')
        lector.permisos.add(ver)
        cls.lector = Usuario.objects.create_user(email='lector-reportes@example.com', rol=lector)
        cls.sin_permiso = Usuario.objects.create_user(email='sin-reportes@example.com')
        cls.superusuario = Usuario.objects.create_superuser(email='super-reportes@example.com')
        cls.bodega = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        cls.otra = Bodega.objects.create(nombre='Bodega Norte', direccion='Norte', activa=False)
        cls.producto = Producto.objects.create(sku='REP-1', nombre='Martillo')
        cls.stock = StockBodega.objects.create(producto=cls.producto, bodega=cls.bodega, cantidad_total=13)
        cls.entrada = TipoMovimiento.objects.create(nombre='ENTRADA', operacion='+')
        cls.salida = TipoMovimiento.objects.create(nombre='SALIDA', operacion='-')
        cls.motivo = MotivoMerma.objects.create(descripcion='Daño en Bodega')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def consulta(self, **params):
        return self.client.get(ROOT + 'consulta/', {'informe': 'existencias', 'bodega': self.bodega.pk, **params})

    def movimiento(self, cantidad, entrada=True, fecha=None, **extra):
        mov = Movimiento.objects.create(tipo=extra.pop('tipo', self.entrada if entrada else self.salida),
            bodega=extra.pop('bodega', self.bodega), usuario=self.admin, documento_referencia=extra.pop('referencia', 'Guía de prueba'))
        if fecha:
            Movimiento.objects.filter(pk=mov.pk).update(fecha_creacion=fecha)
        return DetalleMovimiento.objects.create(movimiento=mov, producto=extra.pop('producto', self.producto), cantidad=cantidad)

    def merma(self, cantidad, fecha=None, **extra):
        m = Merma.objects.create(producto=self.producto, bodega=self.bodega, usuario=self.admin,
                                motivo=self.motivo, cantidad=cantidad, observacion=extra.get('observacion', 'Producto dañado'))
        if fecha:
            Merma.objects.filter(pk=m.pk).update(fecha_creacion=fecha)
        return m

    def resumen(self, r):
        return {v['etiqueta']: v['valor'] for v in r.data['meta']['resumen']}

    def csv(self, **params):
        r = self.client.get(ROOT + 'exportar/', {'informe': 'existencias', 'bodega': self.bodega.pk, **params})
        self.assertEqual(r.status_code, 200, getattr(r, 'data', None))
        contenido = b''.join(r.streaming_content)
        # El cliente de pruebas cierra la respuesta al consumir el streaming.
        self.assertTrue(r.closed)
        self.assertTrue(contenido.startswith(b'\xef\xbb\xbf'))
        self.assertIn('no-store', r['Cache-Control'])
        filas = list(csv.reader(io.StringIO(contenido.decode('utf-8-sig')), delimiter=';'))
        indice = next(i for i, fila in enumerate(filas) if fila and fila[0] in ('SKU', 'Fecha / hora'))
        return filas[:indice], filas[indice], filas[indice + 1:]

    def test_permisos_independientes_para_consultar_y_exportar(self):
        self.client.force_authenticate(self.lector)
        self.assertEqual(self.consulta().status_code, 200)
        self.assertFalse(self.consulta().data['meta']['permisos']['exportar'])
        for ruta in ('exportar/', 'imprimir/'):
            self.assertEqual(self.client.get(ROOT + ruta, {'bodega': self.bodega.pk}).status_code, 403)
        self.client.force_authenticate(self.sin_permiso)
        for ruta in ('consulta/', 'opciones/', 'productos/', 'exportar/', 'imprimir/'):
            self.assertEqual(self.client.get(ROOT + ruta, {'bodega': self.bodega.pk}).status_code, 403)
        self.assertEqual(self.client.get(ROOT + 'acceso/').data['data'], {'ver': False, 'exportar': False})
        self.client.force_authenticate(self.superusuario)
        self.assertEqual(self.consulta().status_code, 200)

    def test_cuenta_y_rol_desactivados_no_permiten_lectura_ni_exportacion(self):
        for objeto, campo in ((self.admin, 'activo'), (self.admin.rol, 'activo')):
            setattr(objeto, campo, False); objeto.save(update_fields=[campo])
            self.assertEqual(self.consulta().status_code, 403)
            self.assertEqual(self.client.get(ROOT + 'exportar/', {'bodega': self.bodega.pk}).status_code, 403)
            setattr(objeto, campo, True); objeto.save(update_fields=[campo])

    def test_sin_sesion_y_metodos_de_escritura_rechazados(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.consulta().status_code, 401)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(ROOT + 'consulta/', {}).status_code, 405)

    def test_stock_y_minimo_unicos_respetan_la_bodega(self):
        StockBodega.objects.filter(pk=self.stock.pk).update(cantidad_total=15)
        StockBodega.objects.create(producto=self.producto, bodega=self.otra, cantidad_total=100)
        StockMinimo.objects.create(producto=self.producto, bodega=self.bodega, cantidad_minima=15)
        r = self.consulta()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['results'][0]['stock'], 15)
        self.assertEqual(r.data['results'][0]['minimo'], 15)
        self.assertEqual(r.data['results'][0]['estado'], 'Stock bajo')
        self.assertEqual(self.resumen(r)['Unidades'], 15)
        self.assertIn('no-store', r['Cache-Control'])

    def test_critico_incluye_agotados_sin_stock_y_omite_bajo_con_minimo_cero(self):
        Producto.objects.create(sku='REP-2', nombre='Sin registro')
        Producto.objects.create(sku='REP-3', nombre='Inactivo agotado', activo=False)
        r = self.consulta(informe='critico')
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['stock'], 0)
        self.assertEqual(r.data['results'][0]['estado'], 'Agotado')
        self.assertEqual(self.consulta(informe='critico', productos='todos').data['count'], 2)

    def test_stock_paginado_y_totales_son_de_todo_el_filtro(self):
        Producto.objects.bulk_create([Producto(sku=f'PAG-{n}', nombre=f'Paginado {n:03d}') for n in range(55)])
        r = self.consulta(search='Paginado', page=2)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['count'], 55)
        self.assertEqual(len(r.data['results']), 25)
        self.assertEqual(self.resumen(r)['Productos'], 55)
        self.assertEqual(self.consulta(search='Paginado', page='last').data['results'].__len__(), 5)

    def test_validacion_de_filtros_no_simula_stock_historico(self):
        for params in ({'bodega': 99999}, {'bodega': ''}, {'bodega': 9223372036854775808},
                       {'desde': '2026-01-01'}, {'hasta': 'fecha'}, {'informe': 'otro'},
                       {'informe': 'kardex'}, {'informe': 'kardex', 'producto': 99999},
                       {'informe': 'kardex', 'producto': self.producto.pk, 'search': 'Martillo'},
                       {'informe': 'mermas', 'desde': '2026-10-30', 'hasta': '2026-10-01'},
                       {'informe': 'movimientos', 'hasta': '9999-12-31'}, {'tipo': 'SALIDA'}):
            with self.subTest(params=params): self.assertEqual(self.consulta(**params).status_code, 400)

    def test_historial_y_productos_conservan_inactivos_y_bodegas_inactivas(self):
        Producto.objects.filter(pk=self.producto.pk).update(activo=False)
        self.movimiento(5, bodega=self.otra)
        r = self.consulta(informe='movimientos', bodega=self.otra.pk)
        self.assertEqual(r.data['count'], 1)
        opciones = self.client.get(ROOT + 'opciones/').data['data']
        self.assertEqual(len(opciones['bodegas']), 2)
        self.assertEqual(self.client.get(ROOT + 'productos/', {'search': 'REP-1'}).data['results'][0]['activo'], False)

    def test_fechas_locales_incluyen_dia_completo_y_excluyen_siguiente(self):
        for fecha in (datetime(2026, 10, 20, 0, 0, tzinfo=ZONA), datetime(2026, 10, 20, 23, 59, 59, tzinfo=ZONA), datetime(2026, 10, 21, 0, 0, tzinfo=ZONA)):
            self.movimiento(1, fecha=fecha); self.merma(1, fecha=fecha)
        for informe in ('movimientos', 'mermas'):
            r = self.consulta(informe=informe, desde='2026-10-20', hasta='2026-10-20')
            self.assertEqual(r.data['count'], 2)
            self.assertEqual(r.data['meta']['zona_horaria'], 'America/Santiago')

    def test_filtros_movimientos_bodega_producto_tipo_y_fechas(self):
        self.movimiento(3, fecha=datetime(2026, 10, 20, 12, tzinfo=tz.utc))
        self.movimiento(2, entrada=False)
        self.movimiento(6, bodega=self.otra)
        r = self.consulta(informe='movimientos', tipo='ENTRADA', search='REP-1', desde='2026-10-20', hasta='2026-10-20')
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(self.resumen(r)['Entradas'], 3)

    def test_kardex_concilia_stock_inicial_heredado_y_mermas(self):
        self.movimiento(10); self.movimiento(4, entrada=False); self.merma(3)
        r = self.consulta(informe='kardex', producto=self.producto.pk)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual([f['saldo'] for f in r.data['results']], [20, 16, 13])
        self.assertEqual(self.resumen(r)['Saldo inicial calculado'], 10)
        self.assertEqual(self.resumen(r)['Saldo final calculado'], 13)
        self.assertIn('antes del historial', ' '.join(r.data['meta']['notas']))

    def test_kardex_periodo_saldo_inicial_y_final_descuentan_eventos_posteriores(self):
        self.movimiento(10, fecha=datetime(2026, 10, 1, 12, tzinfo=tz.utc))
        self.movimiento(4, entrada=False, fecha=datetime(2026, 10, 15, 12, tzinfo=tz.utc))
        self.merma(3, fecha=datetime(2026, 10, 25, 12, tzinfo=tz.utc))
        r = self.consulta(informe='kardex', producto=self.producto.pk, desde='2026-10-10', hasta='2026-10-20')
        self.assertEqual(self.resumen(r)['Saldo inicial calculado'], 20)
        self.assertEqual(self.resumen(r)['Saldo final calculado'], 16)
        self.assertEqual(r.data['results'][0]['saldo'], 16)

    def test_kardex_pagina_dos_continua_saldo_con_fechas_iguales(self):
        fecha = datetime(2026, 10, 20, 12, tzinfo=tz.utc)
        for _ in range(30): self.movimiento(1, fecha=fecha)
        for _ in range(3): self.merma(1, fecha=fecha)
        r1 = self.consulta(informe='kardex', producto=self.producto.pk)
        r2 = self.consulta(informe='kardex', producto=self.producto.pk, page=2)
        self.assertEqual(r1.data['count'], 33)
        self.assertEqual(r2.data['results'][0]['saldo'], r1.data['results'][-1]['saldo'] + 1)
        self.assertEqual(r2.data['results'][-1]['saldo'], 13)
        self.assertEqual(r2.data['results'][-1]['tipo'], 'Merma')
        self.assertEqual(len({f['id'] for f in r1.data['results'] + r2.data['results']}), 33)

    def test_transferencia_no_se_cuenta_dos_veces_en_kardex(self):
        transferencia = Transferencia.objects.create(bodega_origen=self.bodega, bodega_destino=self.otra, usuario=self.admin, estado='COMPLETADA')
        DetalleTransferencia.objects.create(transferencia=transferencia, producto=self.producto, cantidad=2)
        tipo = TipoMovimiento.objects.create(nombre='TRANSFERENCIA_SALIDA', operacion='-')
        self.movimiento(2, entrada=False, tipo=tipo, referencia=f'Transferencia #{transferencia.pk}')
        r = self.consulta(informe='kardex', producto=self.producto.pk)
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['tipo'], 'Transferencia: salida')
        self.assertEqual(self.resumen(r)['Salidas (incluye mermas)'], 2)
        self.assertEqual(r.data['results'][0]['saldo'], 13)

    def test_periodo_sin_eventos_conserva_saldo_y_reporta_cero_filas(self):
        self.movimiento(2, fecha=datetime(2026, 10, 25, 12, tzinfo=tz.utc))
        r = self.consulta(informe='kardex', producto=self.producto.pk, desde='2026-10-01', hasta='2026-10-02')
        self.assertEqual(r.data['count'], 0)
        self.assertEqual(self.resumen(r)['Saldo inicial calculado'], 11)
        self.assertEqual(self.resumen(r)['Saldo final calculado'], 11)

    def test_csv_exporta_todos_los_resultados_sin_limitarse_a_pagina_visible(self):
        for _ in range(31): self.movimiento(1)
        _, cabecera, filas = self.csv(informe='movimientos', page=2)
        self.assertEqual(len(filas), 31)
        self.assertIn('Responsable', cabecera)

    def test_csv_kardex_conserva_saldo_al_cruzar_lotes(self):
        mov = Movimiento.objects.create(tipo=self.entrada, bodega=self.bodega, usuario=self.admin)
        DetalleMovimiento.objects.bulk_create([
            DetalleMovimiento(movimiento=mov, producto=self.producto, cantidad=1) for _ in range(1003)
        ])
        meta, cabecera, filas = self.csv(informe='kardex', producto=self.producto.pk)
        self.assertEqual(len(filas), 1003)
        saldo = cabecera.index('Saldo')
        self.assertEqual(int(filas[1000][saldo]), int(filas[999][saldo]) + 1)
        self.assertEqual(filas[-1][saldo], '13')
        self.assertIn(['Saldo inicial calculado', '-990'], meta)

    def test_fechas_cubren_el_dia_largo_de_cambio_de_horario(self):
        # El 4 de abril incluye dos horas 23:xx en Santiago, con offsets distintos.
        for fecha in (datetime(2026, 4, 5, 2, 30, tzinfo=tz.utc),
                      datetime(2026, 4, 5, 3, 30, tzinfo=tz.utc),
                      datetime(2026, 4, 5, 4, 0, tzinfo=tz.utc)):
            self.movimiento(1, fecha=fecha)
        r = self.consulta(informe='movimientos', desde='2026-04-04', hasta='2026-04-04')
        self.assertEqual(r.data['count'], 2)

    def test_csv_escapa_formulas_y_conserva_numeros_negativos_y_unicode(self):
        Producto.objects.filter(pk=self.producto.pk).update(nombre='=HYPERLINK("malicioso") → Niño')
        _, cabecera, filas = self.csv()
        self.assertTrue(filas[0][cabecera.index('Producto')].startswith("'="))
        self.assertIn('→ Niño', filas[0][cabecera.index('Producto')])
        self.movimiento(30)
        meta, _, _ = self.csv(informe='kardex', producto=self.producto.pk)
        self.assertIn(['Saldo inicial calculado', '-17'], meta)

    def test_imprimible_incluye_contexto_saldos_y_escapa_html(self):
        self.movimiento(1, referencia='<script>alert(1)</script>')
        r = self.client.get(ROOT + 'imprimir/', {'informe': 'kardex', 'bodega': self.bodega.pk, 'producto': self.producto.pk})
        self.assertEqual(r.status_code, 200)
        texto = r.content.decode()
        self.assertIn('Saldo inicial calculado', texto)
        self.assertIn('Bodega Central', texto)
        self.assertIn('reportes@example.com', texto)
        self.assertIn('&lt;script&gt;', texto)
        self.assertNotIn('<script>', texto)

    def test_documento_muy_extenso_pide_acotar_o_descargar_csv(self):
        with patch('django.db.models.query.QuerySet.count', return_value=10001):
            r = self.client.get(ROOT + 'imprimir/', {'bodega': self.bodega.pk})
        self.assertEqual(r.status_code, 400)
        self.assertIn('CSV', str(r.data))

    def test_consultar_no_cambia_stock_ni_crea_movimientos(self):
        with patch('apps.productos.alertas_sms.evaluar_alerta_sms') as sms:
            for informe in ('existencias', 'critico', 'movimientos', 'mermas', 'kardex'):
                self.assertEqual(self.consulta(informe=informe, **({'producto': self.producto.pk} if informe == 'kardex' else {})).status_code, 200)
            sms.assert_not_called()
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 13)
        self.assertEqual(Movimiento.objects.count(), 0)

    def test_una_pagina_no_consulta_cada_producto_por_separado(self):
        with CaptureQueriesContext(connection) as pocas:
            self.consulta()
        Producto.objects.bulk_create([Producto(sku=f'CONS-{n}', nombre=f'Consulta {n}') for n in range(30)])
        with CaptureQueriesContext(connection) as muchas:
            r = self.consulta()
        self.assertEqual(len(pocas), len(muchas))
        self.assertEqual(len(r.data['results']), 25)
