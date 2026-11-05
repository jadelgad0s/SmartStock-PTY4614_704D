"""Estructuras por bodega, referencias sin cambios de stock y escrituras simultáneas."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.usuarios.models import Permiso, Rol, Usuario
from .models import (Bodega, CodigoBarra, Estanteria, Merma, Movimiento, Nivel, Notificacion,
                     Pasillo, Producto, ProductoUbicacion, StockBodega, Transferencia, Ubicacion)

ROOT = '/api/v1/ubicaciones/'


def estructura(bodega, codigo='A'):
    pasillo = Pasillo.objects.create(bodega=bodega, codigo=codigo)
    estante = Estanteria.objects.create(pasillo=pasillo, codigo='E1')
    nivel = Nivel.objects.create(estanteria=estante, codigo='N1')
    espacio = Ubicacion.objects.create(nivel=nivel, codigo='U1')
    return pasillo, estante, nivel, espacio


class UbicacionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(email='ubicaciones@example.com', rol=Rol.objects.create(codigo='administrador', nombre='Administrador'))
        lectura = Permiso.objects.create(codigo='ver_bodega', nombre='Consultar bodegas')
        escritura = Permiso.objects.create(codigo='editar_bodega', nombre='Editar bodegas')
        operador = Rol.objects.create(codigo='operador', nombre='Operador'); operador.permisos.add(lectura)
        encargado = Rol.objects.create(codigo='encargado_bodega', nombre='Encargado'); encargado.permisos.add(lectura, escritura)
        cls.operador = Usuario.objects.create_user(email='lector-ubicaciones@example.com', rol=operador)
        cls.encargado = Usuario.objects.create_user(email='encargado-ubicaciones@example.com', rol=encargado)
        cls.bodega = Bodega.objects.create(nombre='Central')
        cls.otra = Bodega.objects.create(nombre='Norte')
        cls.pasillo, cls.estante, cls.nivel, cls.espacio = estructura(cls.bodega)
        cls.ajenos = estructura(cls.otra)
        cls.producto = Producto.objects.create(sku='UBI-1', nombre='Martillo')
        cls.stock = StockBodega.objects.create(producto=cls.producto, bodega=cls.bodega, cantidad_total=12)
        CodigoBarra.objects.create(producto=cls.producto, codigo='1234567890')

    def setUp(self):
        self.client = APIClient(); self.client.force_authenticate(self.admin)

    def url(self, recurso, bodega=None):
        return ROOT + recurso + '/?bodega=' + str(bodega or self.bodega.pk)

    def post(self, recurso, datos, bodega=None):
        return self.client.post(self.url(recurso, bodega), datos, format='json')

    def asignar(self, **datos):
        return self.post('asignaciones', {'producto_id': self.producto.pk, 'ubicacion_id': self.espacio.pk, **datos})

    def test_acceso_autenticado_y_permiso_real_de_lectura(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url('pasillos')).status_code, 401)
        sin_rol = Usuario.objects.create_user(email='sin-ubicaciones@example.com')
        self.client.force_authenticate(sin_rol)
        self.assertFalse(self.client.get(ROOT + 'opciones/').data['data']['permisos']['ver'])
        self.assertEqual(self.client.get(self.url('pasillos')).status_code, 403)

    def test_operador_consulta_y_encargado_administra_sin_staff(self):
        self.client.force_authenticate(self.operador)
        self.assertEqual(self.client.get(self.url('pasillos')).status_code, 200)
        self.assertEqual(self.post('pasillos', {'codigo': 'B'}).status_code, 403)
        self.assertEqual(self.asignar().status_code, 403)
        self.client.force_authenticate(self.encargado)
        self.assertEqual(self.post('pasillos', {'codigo': 'B'}).status_code, 201)
        self.assertEqual(self.asignar().status_code, 201)

    def test_cuenta_y_rol_desactivados_no_permiten_lectura_ni_escritura(self):
        for objeto, campo in ((self.admin, 'activo'), (self.admin.rol, 'activo')):
            setattr(objeto, campo, False); objeto.save(update_fields=[campo])
            self.assertEqual(self.client.get(self.url('pasillos')).status_code, 403)
            self.assertEqual(self.asignar().status_code, 403)
            setattr(objeto, campo, True); objeto.save(update_fields=[campo])

    def test_superusuario_sin_rol_puede_administrar(self):
        self.client.force_authenticate(Usuario.objects.create_superuser(email='super-ubicaciones@example.com'))
        self.assertEqual(self.post('pasillos', {'codigo': 'SUPER'}).status_code, 201)

    def test_alta_completa_normaliza_codigos_y_resuelve_sus_padres(self):
        padre = None
        for recurso, campo in (('pasillos', None), ('estanterias', 'pasillo'), ('niveles', 'estanteria'), ('espacios', 'nivel')):
            r = self.post(recurso, {'codigo': ' b-02 ', **({campo: padre} if campo else {})})
            self.assertEqual(r.status_code, 201, r.data)
            self.assertEqual(r.data['data']['codigo'], 'B-02')
            padre = r.data['data']['id']
        self.assertEqual(Ubicacion.objects.get(pk=padre).nivel.estanteria.pasillo.bodega, self.bodega)

    def test_codigo_unico_por_padre_y_no_por_toda_la_bodega(self):
        self.assertEqual(self.post('pasillos', {'codigo': 'a'}).status_code, 400)
        self.assertEqual(self.post('pasillos', {'codigo': 'a'}, self.otra.pk).status_code, 400)
        otro = Pasillo.objects.create(bodega=self.bodega, codigo='B')
        self.assertEqual(self.post('estanterias', {'codigo': 'e1', 'pasillo': self.pasillo.pk}).status_code, 400)
        self.assertEqual(self.post('estanterias', {'codigo': 'e1', 'pasillo': otro.pk}).status_code, 201)

    def test_cruce_de_bodega_no_permite_crear_consultar_editar_o_borrar(self):
        for recurso, campo, ajeno in (('estanterias', 'pasillo', self.ajenos[0]), ('niveles', 'estanteria', self.ajenos[1]), ('espacios', 'nivel', self.ajenos[2])):
            self.assertEqual(self.post(recurso, {'codigo': 'NUEVO', campo: ajeno.pk}).status_code, 404)
            self.assertEqual(self.client.get(self.url(recurso) + '&' + campo + '=' + str(ajeno.pk)).status_code, 404)
        for recurso, objeto in zip(('pasillos', 'estanterias', 'niveles', 'espacios'), self.ajenos):
            self.assertEqual(self.client.patch(self.url(f'{recurso}/{objeto.pk}'), {'codigo': 'OTRO'}, format='json').status_code, 404)
            self.assertEqual(self.client.delete(self.url(f'{recurso}/{objeto.pk}')).status_code, 404)
        self.assertEqual(self.asignar(ubicacion_id=self.ajenos[3].pk).status_code, 404)

    def test_editar_codigo_conserva_estructura_y_productos_asignados(self):
        self.asignar()
        r = self.client.patch(self.url(f'pasillos/{self.pasillo.pk}'), {'codigo': ' a-renombrado '}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        referencia = self.client.get(self.url('asignaciones')).data['results'][0]
        self.assertEqual(referencia['ruta'], {'pasillo': 'A-RENOMBRADO', 'estanteria': 'E1', 'nivel': 'N1', 'ubicacion': 'U1'})
        self.assertTrue(ProductoUbicacion.objects.filter(ubicacion=self.espacio).exists())

    def test_no_acepta_cantidades_capacidad_ni_cambios_de_padre(self):
        for valor in ({'codigo': ''}, {'codigo': 'X' * 21}, {'codigo': 'B', 'cantidad': 1}):
            self.assertEqual(self.post('pasillos', valor).status_code, 400)
        r = self.client.patch(self.url(f'espacios/{self.espacio.pk}'), {'codigo': 'B', 'nivel': self.ajenos[2].pk}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.post('espacios', {'nivel': self.nivel.pk, 'codigo': 'B', 'capacidad_maxima': 2}).status_code, 400)
        self.assertEqual(self.asignar(cantidad=4).status_code, 400)
        self.assertEqual(ProductoUbicacion.objects.count(), 0)

    def test_borrado_protegido_de_padres_y_ubicaciones_ocupadas(self):
        referencia = self.asignar().data['data']
        for recurso, objeto in zip(('pasillos', 'estanterias', 'niveles', 'espacios'), (self.pasillo, self.estante, self.nivel, self.espacio)):
            self.assertEqual(self.client.delete(self.url(f'{recurso}/{objeto.pk}')).status_code, 409)
        self.assertEqual(self.client.delete(self.url(f"asignaciones/{referencia['id']}")).status_code, 200)
        for recurso, objeto in reversed(list(zip(('pasillos', 'estanterias', 'niveles', 'espacios'), (self.pasillo, self.estante, self.nivel, self.espacio)))):
            self.assertEqual(self.client.delete(self.url(f'{recurso}/{objeto.pk}')).status_code, 200)

    def test_bodega_inactiva_es_solo_lectura(self):
        referencia = self.asignar().data['data']
        Bodega.objects.filter(pk=self.bodega.pk).update(activa=False)
        self.assertEqual(self.client.get(self.url('pasillos')).status_code, 200)
        self.assertEqual(self.client.get(self.url('asignaciones')).status_code, 200)
        self.assertEqual(self.post('pasillos', {'codigo': 'B'}).status_code, 400)
        self.assertEqual(self.asignar().status_code, 400)
        self.assertEqual(self.client.delete(self.url(f"asignaciones/{referencia['id']}")).status_code, 400)

    def test_asignacion_repetida_es_idempotente_y_producto_puede_tener_varias(self):
        self.assertEqual(self.asignar().status_code, 201)
        self.assertEqual(self.asignar().status_code, 200)
        otra = Ubicacion.objects.create(nivel=self.nivel, codigo='U2')
        self.assertEqual(self.asignar(ubicacion_id=otra.pk).status_code, 201)
        self.assertEqual(ProductoUbicacion.objects.count(), 2)
        self.assertEqual(Auditoria.objects.filter(modelo='ProductoUbicacion', accion='CREATE').count(), 2)

    def test_producto_inactivo_se_consulta_y_se_puede_retirar_su_referencia(self):
        pk = self.asignar().data['data']['id']
        Producto.objects.filter(pk=self.producto.pk).update(activo=False)
        self.assertFalse(self.client.get(self.url('asignaciones')).data['results'][0]['activo'])
        self.assertEqual(self.asignar().status_code, 400)
        self.assertEqual(self.client.delete(self.url(f'asignaciones/{pk}')).status_code, 200)
        self.assertTrue(Producto.objects.filter(pk=self.producto.pk).exists())

    def test_cantidades_heredadas_no_se_modifican_ni_se_borran(self):
        referencia = ProductoUbicacion.objects.create(producto=self.producto, ubicacion=self.espacio, cantidad=3)
        self.assertEqual(self.client.get(self.url('asignaciones')).data['results'][0]['cantidad_heredada'], 3)
        self.assertEqual(self.asignar().status_code, 200)
        self.assertEqual(self.client.delete(self.url(f'asignaciones/{referencia.pk}')).status_code, 409)
        referencia.refresh_from_db(); self.assertEqual(referencia.cantidad, 3)

    def test_asignar_y_retirar_conserva_stock_y_no_crea_operaciones_ni_sms(self):
        with patch('apps.productos.alertas_sms.evaluar_alerta_sms') as sms:
            pk = self.asignar().data['data']['id']
            self.client.delete(self.url(f'asignaciones/{pk}'))
        sms.assert_not_called()
        self.stock.refresh_from_db(); self.assertEqual(self.stock.cantidad_total, 12)
        for modelo in (Movimiento, Transferencia, Merma): self.assertEqual(modelo.objects.count(), 0)
        self.assertEqual(Notificacion.objects.filter(usuario_destino=self.admin).count(), 2)
        self.assertTrue(Notificacion.objects.filter(link=f'/ubicaciones/?bodega={self.bodega.pk}').exists())

    def test_buscador_por_codigo_de_barra_y_ruta_y_filtro_por_producto_o_ubicacion(self):
        self.asignar()
        for texto in ('martillo', 'UBI-1', '1234567890', 'E1', 'N1'):
            r = self.client.get(self.url('asignaciones') + '&search=' + texto)
            self.assertEqual(r.data['count'], 1, r.data)
        self.assertEqual(self.client.get(self.url('productos') + '&search=1234567890').data['count'], 1)
        self.assertEqual(self.client.get(self.url('asignaciones') + '&producto=' + str(self.producto.pk)).data['count'], 1)
        self.assertEqual(self.client.get(self.url('asignaciones') + '&ubicacion=' + str(self.ajenos[3].pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url('asignaciones', self.otra.pk)).data['count'], 0)

    def test_listados_y_busqueda_paginados_sin_duplicar_productos_por_codigos(self):
        CodigoBarra.objects.create(producto=self.producto, codigo='1234567891')
        self.assertEqual(self.client.get(self.url('productos') + '&search=123456789').data['count'], 1)
        Pasillo.objects.bulk_create([Pasillo(bodega=self.bodega, codigo=f'P{i:02}') for i in range(30)])
        r = self.client.get(self.url('pasillos'))
        self.assertEqual(r.data['count'], 31); self.assertEqual(len(r.data['results']), 25)
        self.assertEqual(len(self.client.get(self.url('pasillos') + '&page=last').data['results']), 6)
        self.assertEqual(self.client.get(self.url('pasillos') + '&search=P29').data['count'], 1)

    def test_parametros_invalidos_son_errores_y_no_crean_registros(self):
        for query in ('', '?bodega=abc', '?bodega=-1', '?bodega=1&producto=0', '?bodega=1&ubicacion=no'):
            self.assertEqual(self.client.get(ROOT + 'asignaciones/' + query).status_code, 400)
        self.assertEqual(self.client.get(self.url('estanterias')).status_code, 400)

    def test_fallo_de_auditoria_revierte_alta_y_retiro(self):
        with patch('apps.productos.views_ubicaciones.registrar_auditoria', side_effect=RuntimeError('Prueba')):
            with self.assertRaises(RuntimeError): self.asignar()
        self.assertFalse(ProductoUbicacion.objects.exists())
        pk = self.asignar().data['data']['id']
        with patch('apps.productos.views_ubicaciones.registrar_auditoria', side_effect=RuntimeError('Prueba')):
            with self.assertRaises(RuntimeError): self.client.delete(self.url(f'asignaciones/{pk}'))
        self.assertTrue(ProductoUbicacion.objects.filter(pk=pk).exists())

    def test_pantalla_reutiliza_menu_bodegas_y_no_incluye_sus_formularios(self):
        self.client.force_login(self.admin)
        r = self.client.get('/ubicaciones/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Ubicaciones físicas')
        self.assertContains(r, 'id="menu-sistema-title"')
        self.assertContains(r, 'id="modalAsignarUbicacion"')
        self.assertNotContains(r, 'id="modalEntidad"')
        self.assertContains(r, 'js/ubicaciones.js')


@override_settings(SMS_ALERTAS_ACTIVAS=False)
class ConcurrenciaUbicacionesTests(TransactionTestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_superuser(email='ubicaciones-concurrentes@example.com')
        self.bodega = Bodega.objects.create(nombre='Prueba')
        self.espacio = estructura(self.bodega)[3]
        self.producto = Producto.objects.create(sku='UBI-CON', nombre='Concurrente')

    def simultaneos(self, operacion):
        barrera = Barrier(2)
        def ejecutar(i):
            close_old_connections()
            try:
                c = APIClient(); c.force_authenticate(Usuario.objects.get(pk=self.usuario.pk))
                barrera.wait(timeout=10)
                return operacion(c, i)
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: return list(pool.map(ejecutar, range(2)))

    @skipUnlessDBFeature('has_select_for_update')
    def test_altas_simultaneas_de_codigo_no_duplican_el_pasillo(self):
        respuestas = self.simultaneos(lambda c, i: c.post(ROOT + f'pasillos/?bodega={self.bodega.pk}', {'codigo': 'NUEVO' if i else 'nuevo'}, format='json').status_code)
        self.assertEqual(sorted(respuestas), [201, 400])
        self.assertEqual(Pasillo.objects.filter(bodega=self.bodega, codigo='NUEVO').count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_asignaciones_simultaneas_generan_una_sola_referencia(self):
        respuestas = self.simultaneos(lambda c, _: c.post(ROOT + f'asignaciones/?bodega={self.bodega.pk}', {'producto_id': self.producto.pk, 'ubicacion_id': self.espacio.pk}, format='json').status_code)
        self.assertEqual(sorted(respuestas), [200, 201])
        self.assertEqual(ProductoUbicacion.objects.count(), 1)
        self.assertEqual(ProductoUbicacion.objects.get().cantidad, 0)

    @skipUnlessDBFeature('has_select_for_update')
    def test_asignar_mientras_se_elimina_ubicacion_no_borra_productos(self):
        def operacion(c, i):
            if i: return c.delete(ROOT + f'espacios/{self.espacio.pk}/?bodega={self.bodega.pk}').status_code
            return c.post(ROOT + f'asignaciones/?bodega={self.bodega.pk}', {'producto_id': self.producto.pk, 'ubicacion_id': self.espacio.pk}, format='json').status_code
        respuestas = self.simultaneos(operacion)
        self.assertIn(respuestas, ([201, 409], [404, 200]))
        self.assertTrue(Producto.objects.filter(pk=self.producto.pk).exists())
        self.assertEqual(ProductoUbicacion.objects.count(), int(respuestas[0] == 201))
