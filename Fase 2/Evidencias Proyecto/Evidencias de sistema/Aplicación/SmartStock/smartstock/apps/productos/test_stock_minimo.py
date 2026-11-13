"""Configuración de mínimos por bodega y su efecto en catálogo y Dashboard."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.usuarios.models import Permiso, Rol, Usuario
from .models import Bodega, CodigoBarra, Producto, StockBodega, StockMinimo

ROOT = '/api/v1/productos/'


class StockMinimoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        rol = Rol.objects.create(nombre='Encargado', codigo='encargado_bodega')
        ver = Permiso.objects.create(codigo='ver_producto', nombre='Ver productos', modulo='productos')
        rol.permisos.add(ver, Permiso.objects.create(codigo='editar_producto', nombre='Editar producto', modulo='productos'))
        cls.editor = Usuario.objects.create_user(email='minimo@example.com', nombres='Encargado', apellidos='Bodega', rol=rol)
        cls.admin = Usuario.objects.create_superuser(email='minimo-admin@example.com')
        lector = Rol.objects.create(nombre='Lector', codigo='operador')
        lector.permisos.add(ver)
        cls.lector = Usuario.objects.create_user(email='minimo-lector@example.com', nombres='Solo', apellidos='Lectura', rol=lector)
        cls.central = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        cls.otra = Bodega.objects.create(nombre='Anexo', direccion='Anexo')
        cls.cerrada = Bodega.objects.create(nombre='Cerrada', direccion='Cerrada', activa=False)
        cls.p = Producto.objects.create(sku='MINIMO-01', nombre='Producto con mínimo pendiente', descripcion='Conservar descripción.', precio_referencia='1234.50')
        cls.codigo = CodigoBarra.objects.create(producto=cls.p, codigo='MINIMO-CODIGO', es_principal=True)
        StockBodega.objects.create(producto=cls.p, bodega=cls.central, cantidad_total=3)
        StockBodega.objects.create(producto=cls.p, bodega=cls.otra, cantidad_total=1)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.editor)
        self.dashboard = APIClient()
        self.dashboard.force_authenticate(self.admin)
        self.url = f'{ROOT}{self.p.pk}/stock-minimo/'

    def guardar(self, valor, bodega=None):
        return self.client.patch(self.url, {'bodega': (bodega or self.central).pk, 'cantidad_minima': valor}, format='json')

    def consultar(self, bodega=None):
        return self.client.get(self.url, {'bodega': (bodega or self.central).pk})

    def lista(self, disponibilidad='', bodega=None):
        return self.client.get(ROOT, {'bodega': (bodega or self.central).pk, 'search': self.p.sku, 'disponibilidad': disponibilidad})

    def test_sin_minimo_consulta_cero_y_stock_suficiente_sin_crear_registros(self):
        r = self.consultar()
        self.assertEqual(r.status_code, 200, r.data)
        d = r.data['data']
        self.assertEqual((d['producto_id'], d['bodega_id'], d['stock_actual'], d['cantidad_minima']), (self.p.pk, self.central.pk, 3, 0))
        self.assertFalse(d['configurado']); self.assertFalse(d['alerta_stock_bajo_activa'])
        self.assertEqual(d['estado_stock'], 'suficiente')
        self.assertIn('no-store', r['Cache-Control'])
        self.assertFalse(StockMinimo.objects.exists()); self.assertFalse(Auditoria.objects.exists())

    def test_guardar_minimo_habilita_filtro_detalle_y_alertas_dashboard(self):
        self.assertEqual(self.lista('bajo').data['count'], 0)
        r = self.guardar(5)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['data']['estado_stock'], 'bajo')
        self.assertTrue(r.data['data']['configurado']); self.assertTrue(r.data['data']['alerta_stock_bajo_activa'])
        listado = self.lista('bajo')
        self.assertEqual(listado.data['count'], 1)
        self.assertEqual((listado.data['results'][0]['stock_actual'], listado.data['results'][0]['stock_minimo']), (3, 5))
        dashboard = self.dashboard.get(ROOT + 'dashboard-resumen/', {'bodega': self.central.pk}).data['data']
        self.assertEqual(dashboard['kpi_bajo'], 1)
        self.assertEqual(dashboard['estado_inventario']['bajo'], 1)
        self.assertEqual(dashboard['alertas'][0]['producto_id'], self.p.pk)
        alertas = self.dashboard.get(ROOT + 'dashboard-alertas/', {'bodega': self.central.pk, 'estado': 'bajo'})
        self.assertEqual(alertas.data['count'], 1)
        detalle = self.client.get(f'{ROOT}{self.p.pk}/').data
        self.assertEqual(next(b for b in detalle['existencias'] if b['id'] == self.central.pk)['minimo'], 5)

    def test_minimo_es_local_y_no_modifica_existencias_datos_ni_codigos(self):
        self.guardar(5)
        self.assertEqual(self.consultar(self.otra).data['data']['cantidad_minima'], 0)
        self.assertEqual(self.lista('bajo', self.otra).data['count'], 0)
        self.assertFalse(StockMinimo.objects.filter(bodega=self.otra).exists())
        self.assertEqual(list(StockBodega.objects.filter(producto=self.p).order_by('bodega_id').values_list('cantidad_total', flat=True)), [3, 1])
        self.p.refresh_from_db(); self.codigo.refresh_from_db()
        self.assertEqual(self.p.descripcion, 'Conservar descripción.'); self.assertEqual(str(self.p.precio_referencia), '1234.50')
        self.assertEqual(self.codigo.codigo, 'MINIMO-CODIGO'); self.assertTrue(self.codigo.es_principal)

    def test_umbral_inclusivo_y_reclasificacion_al_reducir_minimo(self):
        self.assertEqual(self.guardar(3).data['data']['estado_stock'], 'bajo')
        self.assertEqual(self.guardar(2).data['data']['estado_stock'], 'suficiente')
        self.assertEqual(self.lista('bajo').data['count'], 0)
        self.assertEqual(self.lista('suficiente').data['count'], 1)
        self.assertEqual(self.dashboard.get(ROOT + 'dashboard-resumen/', {'bodega': self.central.pk}).data['data']['kpi_bajo'], 0)

    def test_cero_desactiva_stock_bajo_pero_no_oculta_agotados(self):
        self.guardar(5)
        r = self.guardar(0)
        self.assertFalse(r.data['data']['alerta_stock_bajo_activa'])
        self.assertEqual(r.data['data']['estado_stock'], 'suficiente')
        self.assertEqual(self.lista('bajo').data['count'], 0)
        StockBodega.objects.filter(producto=self.p, bodega=self.central).update(cantidad_total=0)
        self.assertEqual(self.consultar().data['data']['estado_stock'], 'agotado')
        self.assertEqual(self.lista('agotado').data['count'], 1)
        self.assertEqual(self.dashboard.get(ROOT + 'dashboard-resumen/', {'bodega': self.central.pk}).data['data']['estado_inventario']['agotado'], 1)

    def test_guardar_cero_sin_registro_es_una_configuracion_explicita(self):
        self.assertEqual(self.guardar(0).status_code, 200)
        self.assertTrue(self.consultar().data['data']['configurado'])
        self.assertEqual(StockMinimo.objects.get(producto=self.p, bodega=self.central).cantidad_minima, 0)

    def test_minimo_sin_fila_stock_no_inventa_existencias(self):
        StockBodega.objects.filter(producto=self.p, bodega=self.central).delete()
        r = self.guardar(5)
        self.assertEqual((r.data['data']['stock_actual'], r.data['data']['estado_stock']), (0, 'agotado'))
        self.assertFalse(StockBodega.objects.filter(producto=self.p, bodega=self.central).exists())
        self.assertEqual(self.lista('bajo').data['count'], 0)

    def test_consulta_stock_y_minimo_unicos_sin_modificarlos(self):
        StockBodega.objects.filter(producto=self.p, bodega=self.central).update(cantidad_total=7)
        StockMinimo.objects.create(producto=self.p, bodega=self.central, cantidad_minima=9)
        d = self.consultar().data['data']
        self.assertEqual((d['stock_actual'], d['cantidad_minima'], d['estado_stock']), (7, 9, 'bajo'))
        self.assertEqual(StockMinimo.objects.count(), 1); self.assertFalse(Auditoria.objects.exists())

    def test_guardar_modifica_una_sola_fila_al_bajar_y_desactivar(self):
        StockMinimo.objects.create(producto=self.p, bodega=self.central, cantidad_minima=9)
        self.assertEqual(self.guardar(2).data['data']['estado_stock'], 'suficiente')
        self.assertEqual(list(StockMinimo.objects.values_list('cantidad_minima', flat=True)), [2])
        self.assertEqual(self.lista('bajo').data['count'], 0)
        self.guardar(0)
        self.assertEqual(list(StockMinimo.objects.values_list('cantidad_minima', flat=True)), [0])
        self.assertEqual(StockMinimo.objects.count(), 1)

    def test_guardado_repetido_no_duplica_filas_ni_auditoria(self):
        for _ in range(3):
            self.assertEqual(self.guardar(5).status_code, 200)
        self.assertEqual(StockMinimo.objects.count(), 1)
        self.assertEqual(Auditoria.objects.count(), 1)

    def test_auditoria_identifica_producto_bodega_valor_y_usuario(self):
        self.guardar(5)
        a = Auditoria.objects.get()
        self.assertEqual((a.modelo, a.accion, a.objeto_id, a.usuario_id), ('Producto', 'UPDATE', str(self.p.pk), self.editor.pk))
        self.assertIn(self.p.sku, a.descripcion); self.assertIn(self.central.nombre, a.descripcion)
        self.assertIn('0 → 5', a.descripcion)

    def test_rechaza_minimos_invalidos_sin_crear_registros(self):
        for valor in (-1, 1.5, 'abc', '', None, True, False, 2147483648):
            with self.subTest(valor=valor):
                r = self.guardar(valor)
                self.assertEqual(r.status_code, 400, r.data)
        self.assertFalse(StockMinimo.objects.exists()); self.assertFalse(Auditoria.objects.exists())

    def test_campos_requeridos_y_bodega_valida(self):
        for datos in ({}, {'bodega': self.central.pk}, {'cantidad_minima': 5}, {'bodega': 0, 'cantidad_minima': 5}, {'bodega': True, 'cantidad_minima': 5}):
            with self.subTest(datos=datos):
                self.assertEqual(self.client.patch(self.url, datos, format='json').status_code, 400)
        self.assertEqual(self.client.get(self.url).status_code, 400)
        self.assertFalse(StockMinimo.objects.exists())

    def test_limite_entero_se_guarda_sin_desbordamiento(self):
        r = self.guardar(2147483647)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.consultar().data['data']['cantidad_minima'], 2147483647)

    def test_bodega_inactiva_inexistente_y_producto_inexistente(self):
        for bodega in (self.cerrada.pk, 999999):
            self.assertEqual(self.client.get(self.url, {'bodega': bodega}).status_code, 400)
            self.assertEqual(self.client.patch(self.url, {'bodega': bodega, 'cantidad_minima': 5}, format='json').status_code, 400)
        url = ROOT + '999999/stock-minimo/'
        self.assertEqual(self.client.get(url, {'bodega': self.central.pk}).status_code, 404)
        self.assertEqual(self.client.patch(url, {'bodega': self.central.pk, 'cantidad_minima': 5}, format='json').status_code, 404)
        self.assertFalse(StockMinimo.objects.exists())

    def test_reutiliza_permiso_editar_producto_y_lectura_no_puede_guardar(self):
        self.assertTrue(self.client.get(ROOT + 'opciones/').data['data']['permisos']['configurar_minimo'])
        self.client.force_authenticate(self.lector)
        self.assertEqual(self.consultar().status_code, 200)
        self.assertFalse(self.client.get(ROOT + 'opciones/').data['data']['permisos']['configurar_minimo'])
        self.assertEqual(self.guardar(5).status_code, 403)
        self.assertFalse(StockMinimo.objects.exists())
        self.editor.rol.permisos.clear()
        self.client.force_authenticate(self.editor)
        self.assertEqual(self.guardar(5).status_code, 403)

    def test_superusuario_puede_guardar_y_cuenta_inactiva_o_anonima_no_puede(self):
        self.editor.is_superuser = True; self.editor.rol = None; self.editor.save()
        self.assertTrue(self.client.get(ROOT + 'opciones/').data['data']['permisos']['configurar_minimo'])
        self.assertEqual(self.guardar(5).status_code, 200)
        self.editor.activo = False; self.editor.save()
        self.assertEqual(self.guardar(2).status_code, 403); self.assertEqual(self.consultar().status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.guardar(2).status_code, 401); self.assertEqual(self.consultar().status_code, 401)
        self.assertEqual(StockMinimo.objects.get().cantidad_minima, 5)

    def test_fallo_auditoria_revierte_alta_y_modificacion_de_minimos(self):
        for existentes in (False, True):
            if existentes:
                StockMinimo.objects.create(producto=self.p, bodega=self.central, cantidad_minima=4)
            with self.subTest(existentes=existentes), patch('apps.productos.views.registrar_auditoria', side_effect=RuntimeError('Fallo de auditoría')):
                with self.assertLogs('django.request', level='ERROR'), self.assertRaises(RuntimeError):
                    self.guardar(5)
            self.assertEqual(list(StockMinimo.objects.order_by('id').values_list('cantidad_minima', flat=True)), [4] if existentes else [])
            self.assertFalse(Auditoria.objects.exists())
