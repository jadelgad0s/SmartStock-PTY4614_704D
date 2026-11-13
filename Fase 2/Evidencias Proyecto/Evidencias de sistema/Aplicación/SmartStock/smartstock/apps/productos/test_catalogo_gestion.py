"""Edición sin pérdida de datos, stock compartido, permisos y operaciones atómicas."""
from unittest.mock import patch
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from apps.core.models import Auditoria
from apps.usuarios.models import Permiso, Rol, Usuario
from .models import Bodega, CodigoBarra, Producto, StockBodega, StockMinimo

ROOT = '/api/v1/productos/'


class CatalogoGestionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        rol = Rol.objects.create(nombre='Encargado catálogo', codigo='encargado_bodega')
        for codigo in ('ver_producto', 'crear_producto', 'editar_producto', 'eliminar_producto'):
            rol.permisos.add(Permiso.objects.create(codigo=codigo, nombre=codigo, modulo='productos'))
        cls.usuario = Usuario.objects.create_user(email='catalogo@example.com', nombres='Persona', apellidos='Catálogo', rol=rol)
        admin = Rol.objects.create(nombre='Administrador renombrado', codigo='administrador')
        cls.admin = Usuario.objects.create_user(email='admin-cat@example.com', nombres='Admin', apellidos='Catálogo', rol=admin)
        lector = Rol.objects.create(nombre='Lector', codigo='operador')
        lector.permisos.add(Permiso.objects.get(codigo='ver_producto'))
        cls.lector = Usuario.objects.create_user(email='lector-cat@example.com', nombres='Lector', apellidos='Catálogo', rol=lector)
        cls.central = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        cls.otra = Bodega.objects.create(nombre='Anexo', direccion='Anexo')
        cls.cerrada = Bodega.objects.create(nombre='Cerrada', direccion='Cerrada', activa=False)
        cls.p = Producto.objects.create(sku='CAT-EDIT', nombre='Producto con descripción', descripcion='Primera línea.\nDetalles que deben conservarse.', precio_referencia='1234.50')
        cls.barra = CodigoBarra.objects.create(producto=cls.p, codigo='7801234567890', tipo='BARRA', es_principal=True)
        cls.qr = CodigoBarra.objects.create(producto=cls.p, codigo='https://ejemplo.cl/p?id=1,2', tipo='QR', es_principal=False)
        StockBodega.objects.create(producto=cls.p, bodega=cls.central, cantidad_total=3)
        StockMinimo.objects.create(producto=cls.p, bodega=cls.central, cantidad_minima=5)
        StockBodega.objects.create(producto=cls.p, bodega=cls.otra, cantidad_total=80)
        StockMinimo.objects.create(producto=cls.p, bodega=cls.otra, cantidad_minima=2)
        StockBodega.objects.create(producto=cls.p, bodega=cls.cerrada, cantidad_total=1000)
        cls.sin = Producto.objects.create(sku='SIN-FILA', nombre='Sin stock registrado')
        cls.inactivo = Producto.objects.create(sku='INACTIVO', nombre='Producto inactivo', activo=False)
        StockBodega.objects.create(producto=cls.inactivo, bodega=cls.central, cantidad_total=9)

    def setUp(self):
        self.client = APIClient(); self.client.force_authenticate(self.usuario)

    def detalle(self, p=None):
        r = self.client.get(ROOT + str((p or self.p).pk) + '/')
        self.assertEqual(r.status_code, 200, r.data)
        return r.data

    def editar(self, data):
        return self.client.patch(ROOT + str(self.p.pk) + '/', data, format='json')

    def test_detalle_crudo_incluye_descripcion_codigos_completos_y_stock_por_bodega(self):
        d = self.detalle()
        self.assertNotIn('data', d)  # Se conserva el contrato DRF de retrieve.
        self.assertEqual(d['descripcion'], self.p.descripcion)
        self.assertEqual(len(d['codigos_barra']), 2)
        self.assertTrue(d['codigos_barra'][0]['es_principal'])
        self.assertEqual(d['codigos_barra'][1]['tipo'], 'QR')
        bodegas = {b['id']: b for b in d['existencias']}
        self.assertNotIn(self.cerrada.pk, bodegas)
        self.assertEqual(bodegas[self.central.pk]['estado'], 'bajo')
        self.assertEqual(bodegas[self.otra.pk]['stock'], 80)
        self.assertEqual(bodegas[self.otra.pk]['estado'], 'suficiente')

    def test_editar_nombre_o_precio_conserva_descripcion_codigos_tipos_principal_e_ids(self):
        ids = list(self.p.codigos_barra.values_list('pk', flat=True))
        r = self.editar({'nombre': 'Nombre actualizado', 'precio_referencia': '9876.54'})
        self.assertEqual(r.status_code, 200, r.data)
        self.p.refresh_from_db(); self.barra.refresh_from_db(); self.qr.refresh_from_db()
        self.assertEqual(self.p.descripcion, 'Primera línea.\nDetalles que deben conservarse.')
        self.assertEqual(str(self.p.precio_referencia), '9876.54')
        self.assertEqual(list(self.p.codigos_barra.values_list('pk', flat=True)), ids)
        self.assertTrue(self.barra.es_principal); self.assertEqual(self.qr.tipo, 'QR')
        self.assertTrue(Auditoria.objects.filter(modelo='Producto', accion='UPDATE', objeto_id=str(self.p.pk)).exists())

    def test_edicion_explicita_de_codigos_conserva_ids_y_fechas_y_cambia_principal(self):
        fechas = {c.pk: c.fecha_creacion for c in self.p.codigos_barra.all()}
        r = self.editar({'codigos_barra': [
            {'codigo': self.qr.codigo, 'tipo': 'QR', 'es_principal': True},
            {'codigo': self.barra.codigo, 'tipo': 'BARRA', 'es_principal': False},
        ]})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual({c.pk: c.fecha_creacion for c in self.p.codigos_barra.all()}, fechas)
        self.qr.refresh_from_db(); self.barra.refresh_from_db()
        self.assertTrue(self.qr.es_principal); self.assertFalse(self.barra.es_principal)
        self.assertEqual(next(c for c in r.data['data']['codigos_barra'] if c['id'] == self.qr.pk)['tipo'], 'QR')

    def test_quitar_y_agregar_codigos_solo_modifica_las_filas_elegidas(self):
        r = self.editar({'codigos_barra': [{'codigo': self.qr.codigo, 'tipo': 'QR', 'es_principal': True}, {'codigo': 'COD-NUEVO', 'tipo': 'BARRA', 'es_principal': False}]})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(CodigoBarra.objects.filter(pk=self.barra.pk).exists())
        self.assertTrue(CodigoBarra.objects.filter(pk=self.qr.pk).exists())
        self.assertEqual(self.p.codigos_barra.count(), 2)
        self.assertEqual(self.editar({'codigos_barra': []}).status_code, 200)
        self.assertEqual(self.p.codigos_barra.count(), 0)

    def test_rechaza_codigo_ajeno_repetidos_y_dos_principales_sin_perder_datos(self):
        CodigoBarra.objects.create(producto=self.sin, codigo='OTRO-CODIGO')
        for lista in ([{'codigo': 'OTRO-CODIGO'}], [{'codigo': 'DUP'}, {'codigo': 'DUP'}], [{'codigo': 'A', 'es_principal': True}, {'codigo': 'B', 'es_principal': True}]):
            with self.subTest(lista=lista):
                r = self.editar({'nombre': 'No debe guardarse', 'codigos_barra': lista})
                self.assertEqual(r.status_code, 400, r.data)
                self.assertIn('codigos_barra', r.data['errores'])
                self.p.refresh_from_db(); self.assertEqual(self.p.nombre, 'Producto con descripción')
                self.assertEqual(self.p.codigos_barra.count(), 2)

    def test_sku_se_normaliza_antes_del_patron_y_no_se_repite_entre_inactivos(self):
        r = self.client.post(ROOT, {'sku': '  fer-nuevo  ', 'nombre': 'Nuevo', 'precio_referencia': '0.01'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['data']['sku'], 'FER-NUEVO')
        for sku in ('FER-NUEVO', 'inactivo', 'CON ESPACIO', 'X' * 51):
            self.assertEqual(self.client.post(ROOT, {'sku': sku, 'nombre': 'Otro'}, format='json').status_code, 400)
        self.assertEqual(Producto.objects.filter(sku='FER-NUEVO').count(), 1)

    def test_precio_cero_y_decimales_se_conservan_y_valores_invalidos_se_rechazan(self):
        for valor in ('0.00', '0.01', '1234.50', '9999999999.99'):
            r = self.editar({'precio_referencia': valor})
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(r.data['data']['precio_referencia'], valor)
        for valor in ('', 'abc', '-1', '1.234', '10000000000.00'):
            self.assertEqual(self.editar({'precio_referencia': valor}).status_code, 400)

    def test_stock_filtrado_no_mezcla_bodegas_y_sin_fila_es_cero(self):
        r = self.client.get(ROOT, {'bodega': self.central.pk, 'search': self.p.sku})
        self.assertEqual(r.data['bodega']['id'], self.central.pk)
        p = r.data['results'][0]; self.assertEqual(p['stock_actual'], 3); self.assertEqual(p['stock_minimo'], 5); self.assertEqual(p['estado_stock'], 'bajo')
        r = self.client.get(ROOT, {'bodega': self.otra.pk, 'search': self.p.sku})
        self.assertEqual(r.data['results'][0]['stock_actual'], 80)
        self.assertEqual(r.data['results'][0]['estado_stock'], 'suficiente')
        r = self.client.get(ROOT, {'bodega': self.central.pk, 'search': self.sin.sku})
        self.assertEqual(r.data['results'][0]['stock_actual'], 0)
        self.assertEqual(r.data['results'][0]['estado_stock'], 'agotado')

    def test_consulta_sin_bodega_conserva_total_global_sin_clasificarlo_como_local(self):
        r = self.client.get(ROOT, {'search': self.p.sku})
        self.assertIsNone(r.data['bodega'])
        self.assertEqual(r.data['results'][0]['stock_actual'], 1083)
        self.assertIsNone(r.data['results'][0]['stock_minimo'])
        self.assertIsNone(r.data['results'][0]['estado_stock'])

    def test_filtros_estado_disponibilidad_busqueda_y_paginacion_se_combinan(self):
        Producto.objects.bulk_create([Producto(sku=f'PAG-{i:03}', nombre=f'Producto paginado {i:03}') for i in range(55)])
        params = {'bodega': self.central.pk, 'activo': 'true', 'disponibilidad': 'agotado', 'search': 'paginado', 'ordering': '-nombre,-id'}
        ids = []
        for pagina, cantidad in ((1, 25), (2, 25), (3, 5)):
            r = self.client.get(ROOT, {**params, 'page': pagina})
            self.assertEqual(r.status_code, 200, r.data); self.assertEqual(r.data['count'], 55); self.assertEqual(len(r.data['results']), cantidad)
            ids.extend(p['id'] for p in r.data['results'])
        self.assertEqual(len(set(ids)), 55)
        r = self.client.get(ROOT, {'bodega': self.central.pk, 'activo': 'false', 'disponibilidad': 'suficiente'})
        self.assertEqual([p['id'] for p in r.data['results']], [self.inactivo.pk])
        self.assertEqual(self.client.get(ROOT, {'bodega': self.central.pk, 'search': self.qr.codigo}).data['count'], 1)

    def test_estados_coinciden_con_dashboard_y_no_duplican_stock_ni_minimos(self):
        StockBodega.objects.filter(producto=self.p, bodega=self.central).update(cantidad_total=7)
        StockMinimo.objects.filter(producto=self.p, bodega=self.central).update(cantidad_minima=9)
        dashboard = APIClient()
        dashboard.force_authenticate(self.admin)
        d = dashboard.get(ROOT + 'dashboard-resumen/', {'bodega': self.central.pk}).data['data']['estado_inventario']
        for estado, clave in (('suficiente', 'suficiente'), ('bajo', 'bajo'), ('agotado', 'agotado')):
            r = self.client.get(ROOT, {'bodega': self.central.pk, 'activo': 'true', 'disponibilidad': estado})
            self.assertEqual(r.data['count'], d[clave])
        r = self.client.get(ROOT, {'bodega': self.central.pk, 'search': self.p.sku})
        self.assertEqual(r.data['results'][0]['stock_actual'], 7); self.assertEqual(r.data['results'][0]['stock_minimo'], 9)

    def test_validacion_bodega_disponibilidad_busqueda_y_opciones_sin_bodegas(self):
        for params in ({'bodega': 9999}, {'bodega': self.cerrada.pk}, {'bodega': 'x'}, {'disponibilidad': 'bajo'}, {'bodega': self.central.pk, 'disponibilidad': 'otra'}, {'search': 'x' * 201}):
            self.assertEqual(self.client.get(ROOT, params).status_code, 400)
        Bodega.objects.update(activa=False)
        d = self.client.get(ROOT + 'opciones/').data['data']
        self.assertEqual(d['bodegas'], []); self.assertIsNone(d['bodega_predeterminada'])
        self.assertEqual(self.detalle()['existencias'], [])
        self.assertEqual(self.client.get(ROOT).status_code, 200)

    def test_permisos_de_opciones_coinciden_con_escrituras_y_codigo_real_de_rol(self):
        d = self.client.get(ROOT + 'opciones/').data['data']
        self.assertEqual(d['bodega_predeterminada'], self.central.pk)
        self.assertEqual([b['id'] for b in d['bodegas']], [self.otra.pk, self.central.pk])
        for k in ('crear', 'editar', 'desactivar', 'reactivar'): self.assertTrue(d['permisos'][k])
        self.assertFalse(d['permisos']['eliminar_definitivamente'])
        self.client.force_authenticate(self.admin)
        d = self.client.get(ROOT + 'opciones/').data['data']['permisos']
        self.assertTrue(d['eliminar_definitivamente']); self.assertTrue(d['auditoria']); self.assertFalse(d['configuracion'])
        self.client.force_authenticate(self.lector)
        d = self.client.get(ROOT + 'opciones/').data['data']['permisos']
        self.assertFalse(any(d.values()))
        for metodo, ruta in (('post', ROOT), ('patch', ROOT + str(self.p.pk) + '/'), ('delete', ROOT + str(self.p.pk) + '/'), ('post', ROOT + str(self.inactivo.pk) + '/activar/')):
            self.assertEqual(getattr(self.client, metodo)(ruta, {}, format='json').status_code, 403)

    def test_reactivar_con_permiso_de_desactivacion_no_exige_superusuario(self):
        r = self.client.post(ROOT + str(self.inactivo.pk) + '/activar/', {}, format='json')
        self.assertEqual(r.status_code, 200, r.data); self.inactivo.refresh_from_db(); self.assertTrue(self.inactivo.activo)
        self.assertEqual(self.client.delete(ROOT + str(self.inactivo.pk) + '/').status_code, 200)
        self.inactivo.refresh_from_db(); self.assertFalse(self.inactivo.activo)
        self.assertEqual(Auditoria.objects.filter(modelo='Producto', objeto_id=str(self.inactivo.pk)).count(), 2)
        self.client.delete(ROOT + str(self.inactivo.pk) + '/')
        self.assertEqual(Auditoria.objects.filter(modelo='Producto', objeto_id=str(self.inactivo.pk)).count(), 2)

    def test_producto_inactivo_se_puede_editar_con_permiso(self):
        r = self.client.patch(ROOT + str(self.inactivo.pk) + '/', {'descripcion': 'Información actualizada'}, format='json')
        self.assertEqual(r.status_code, 200); self.inactivo.refresh_from_db(); self.assertFalse(self.inactivo.activo)

    def test_eliminacion_definitiva_respeta_historial_y_permite_codigo_sin_referencias(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(ROOT + str(self.p.pk) + '/eliminar-definitivamente/').status_code, 409)
        libre = Producto.objects.create(sku='BORRABLE', nombre='Borrable')
        codigo = CodigoBarra.objects.create(producto=libre, codigo='SOLO-CODIGO')
        r = self.client.delete(ROOT + str(libre.pk) + '/eliminar-definitivamente/')
        self.assertEqual(r.status_code, 200, r.data); self.assertFalse(Producto.objects.filter(pk=libre.pk).exists()); self.assertFalse(CodigoBarra.objects.filter(pk=codigo.pk).exists())

    def test_fallo_auditoria_revierte_alta_edicion_codigos_desactivacion_y_reactivacion(self):
        operaciones = (
            lambda: self.client.post(ROOT, {'sku': 'ROLLBACK', 'nombre': 'Rollback'}, format='json'),
            lambda: self.editar({'descripcion': 'No persistir', 'codigos_barra': []}),
            lambda: self.client.delete(ROOT + str(self.p.pk) + '/'),
            lambda: self.client.post(ROOT + str(self.inactivo.pk) + '/activar/', {}, format='json'),
        )
        for op in operaciones:
            with self.subTest(op=op), patch('apps.productos.views.registrar_auditoria', side_effect=RuntimeError('Fallo de auditoría')):
                with self.assertLogs('django.request', level='ERROR'), self.assertRaises(RuntimeError): op()
            self.p.refresh_from_db(); self.inactivo.refresh_from_db()
            self.assertEqual(self.p.descripcion, 'Primera línea.\nDetalles que deben conservarse.')
            self.assertEqual(self.p.codigos_barra.count(), 2); self.assertTrue(self.p.activo); self.assertFalse(self.inactivo.activo)
            self.assertFalse(Producto.objects.filter(sku='ROLLBACK').exists())

    def test_conflicto_sku_despues_de_validar_devuelve_error_de_campo_y_no_alta_parcial(self):
        with patch('apps.productos.serializers.ProductoCreateUpdateSerializer.validate_sku', return_value=self.p.sku):
            r = self.client.post(ROOT, {'sku': 'OTRO', 'nombre': 'Conflicto', 'codigos_barra': [{'codigo': 'NO-DEBE-QUEDAR'}]}, format='json')
        self.assertEqual(r.status_code, 400, r.data)
        self.assertFalse(CodigoBarra.objects.filter(codigo='NO-DEBE-QUEDAR').exists())
        self.assertFalse(Auditoria.objects.exists())

    def test_listado_25_consulta_stock_y_codigos_sin_n_mas_uno(self):
        productos = Producto.objects.bulk_create([Producto(sku=f'QUERY-{i:03}', nombre=f'Query {i:03}') for i in range(55)])
        CodigoBarra.objects.bulk_create([CodigoBarra(producto=p, codigo=f'QUERYCODE-{i}', es_principal=True) for i, p in enumerate(productos)])
        with CaptureQueriesContext(connection) as consultas:
            r = self.client.get(ROOT, {'bodega': self.central.pk, 'search': 'QUERY-'})
        self.assertEqual(r.status_code, 200); self.assertEqual(len(r.data['results']), 25)
        self.assertLessEqual(len(consultas), 5)
        self.assertTrue(all(p['codigo_principal'] for p in r.data['results']))

    def test_autenticacion_cuenta_activa_y_respuestas_sin_cache(self):
        for ruta in (ROOT, ROOT + 'opciones/', ROOT + str(self.p.pk) + '/'):
            self.assertIn('no-store', self.client.get(ruta)['Cache-Control'])
            self.usuario.activo = False; self.assertEqual(self.client.get(ruta).status_code, 403)
            self.usuario.activo = True; self.client.force_authenticate(None); self.assertEqual(self.client.get(ruta).status_code, 401); self.client.force_authenticate(self.usuario)
