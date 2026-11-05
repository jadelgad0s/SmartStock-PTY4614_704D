"""Avisos únicos en la campana, ligados al cambio y a la cuenta que lo realiza."""
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.usuarios.models import Permiso, Rol, Usuario
from .models import Bodega, CodigoBarra, Merma, Movimiento, Notificacion, Producto, StockBodega, StockMinimo
from .views_notificaciones import notificar_administradores

ROOT = '/api/v1/productos/'
USUARIOS = '/api/v1/usuarios/'


class NotificacionesOperacionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol = Rol.objects.create(nombre='Encargado', codigo='encargado_bodega')
        cls.rol_admin = Rol.objects.create(nombre='Administrador', codigo='administrador')
        for codigo in ('crear_producto', 'editar_producto', 'eliminar_producto', 'registrar_entrada', 'registrar_salida', 'registrar_merma'):
            p = Permiso.objects.create(codigo=codigo, nombre=codigo, modulo='productos')
            cls.rol.permisos.add(p); cls.rol_admin.permisos.add(p)
        cls.admin = Usuario.objects.create_user(email='avisos-admin@example.com', nombres='Admin', apellidos='Uno', rol=cls.rol_admin)
        cls.admin2 = Usuario.objects.create_user(email='avisos-admin2@example.com', nombres='Admin', apellidos='Dos', rol=cls.rol_admin)
        cls.actor = Usuario.objects.create_user(email='avisos-actor@example.com', nombres='Encargado', apellidos='Uno', rol=cls.rol)
        cls.otro = Usuario.objects.create_user(email='avisos-otro@example.com', nombres='Encargado', apellidos='Ajeno', rol=cls.rol)
        cls.inactivo = Usuario.objects.create_user(email='avisos-inactivo@example.com', nombres='Admin', apellidos='Inactivo', rol=cls.rol_admin, activo=False)
        cls.producto = Producto.objects.create(sku='AVISO-01', nombre='Producto de prueba', precio_referencia=1000)
        cls.bodega = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        cls.stock = StockBodega.objects.create(producto=cls.producto, bodega=cls.bodega, cantidad_total=10)

    def setUp(self):
        self.client = APIClient(); self.client.force_authenticate(self.actor)
        self.url = f'{ROOT}{self.producto.pk}/'

    def propios(self, usuario=None):
        return Notificacion.objects.filter(usuario_destino=usuario or self.actor).order_by('id')

    def un_aviso_por_destinatario(self, destinatarios=None):
        esperados = destinatarios or {self.admin.pk, self.admin2.pk, self.actor.pk}
        self.assertEqual(set(Notificacion.objects.values_list('usuario_destino_id', flat=True)), esperados)
        self.assertEqual(Notificacion.objects.count(), len(esperados))

    def test_helper_incluye_actor_y_admins_activos_sin_avisar_a_otro_operador(self):
        notificar_administradores(tipo='OTRO', titulo='Cambio', mensaje='Cambio realizado', link='/productos/', actor_id=self.actor.pk)
        self.un_aviso_por_destinatario()

    def test_administrador_actor_recibe_una_sola_copia(self):
        self.client.force_authenticate(self.admin)
        r = self.client.patch(self.url, {'nombre': 'Nombre cambiado'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.un_aviso_por_destinatario({self.admin.pk, self.admin2.pk})

    def test_crear_producto_deja_aviso_persistido_para_el_actor(self):
        r = self.client.post(ROOT, {'sku': 'AVISO-NUEVO', 'nombre': 'Producto nuevo'}, format='json')
        self.assertEqual(r.status_code, 201, r.data); self.un_aviso_por_destinatario()
        n = self.propios().get(); self.assertEqual(n.titulo, 'Producto creado')
        self.assertIn('Producto nuevo', n.mensaje)
        self.assertEqual(parse_qs(urlsplit(n.link).query)['q'], ['AVISO-NUEVO'])
        bandeja = self.client.get(ROOT + 'notificaciones/no-leidas/').data['data']
        self.assertEqual(bandeja['total'], 1); self.assertEqual(bandeja['items'][0]['id'], n.pk)

    def test_editar_producto_notifica_sin_perder_codigos_ni_stock(self):
        codigo = CodigoBarra.objects.create(producto=self.producto, codigo='AVISO-CODIGO', es_principal=True)
        r = self.client.patch(self.url, {'precio_referencia': '1500'}, format='json')
        self.assertEqual(r.status_code, 200, r.data); self.un_aviso_por_destinatario()
        self.assertEqual(self.propios().get().titulo, 'Producto actualizado')
        self.stock.refresh_from_db(); self.assertEqual(self.stock.cantidad_total, 10)
        self.assertTrue(CodigoBarra.objects.filter(pk=codigo.pk).exists())

    def test_minimo_notifica_con_bodega_y_repetir_no_duplica_el_aviso(self):
        ruta = self.url + 'stock-minimo/'
        for _ in range(2):
            r = self.client.patch(ruta, {'bodega': self.bodega.pk, 'cantidad_minima': 5}, format='json')
            self.assertEqual(r.status_code, 200, r.data)
        self.un_aviso_por_destinatario()
        n = self.propios().get(); self.assertIn('5 unidades', n.mensaje)
        self.assertEqual(parse_qs(urlsplit(n.link).query)['bodega'], [str(self.bodega.pk)])
        self.client.patch(ruta, {'bodega': self.bodega.pk, 'cantidad_minima': 0}, format='json')
        self.assertIn('Aviso de stock bajo desactivado', self.propios().last().mensaje)

    def test_desactivar_y_reactivar_producto_no_duplica_avisos_en_reintentos(self):
        for _ in range(2): self.assertEqual(self.client.delete(self.url).status_code, 200)
        self.assertEqual(self.propios().count(), 1)
        for _ in range(2): self.assertEqual(self.client.post(self.url + 'activar/').status_code, 200)
        self.assertEqual(list(self.propios().values_list('titulo', flat=True)), ['Producto desactivado', 'Producto reactivado'])

    def test_eliminar_producto_libre_conserva_su_nombre_en_la_notificacion(self):
        p = Producto.objects.create(sku='AVISO-LIBRE', nombre='Producto libre')
        self.client.force_authenticate(self.admin)
        r = self.client.delete(f'{ROOT}{p.pk}/eliminar-definitivamente/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(Producto.objects.filter(sku='AVISO-LIBRE').exists())
        self.assertIn('Producto libre', self.propios(self.admin).get().mensaje)

    def test_entrada_y_salida_avisos_para_actor_no_admin_con_stock_resultante(self):
        for tipo, cantidad, restante in (('ENTRADA', 5, 15), ('SALIDA', 2, 13)):
            r = self.client.post(ROOT + 'registrar-movimiento/', {'producto_id': self.producto.pk, 'tipo_movimiento': tipo, 'cantidad': cantidad}, format='json')
            self.assertEqual(r.status_code, 201, r.data)
            self.assertIn(f'{restante} unidades', self.propios().last().mensaje)
        self.assertEqual(self.propios().count(), 2)
        self.assertEqual(Notificacion.objects.count(), 6)
        self.assertFalse(self.propios(self.otro).exists())

    def test_merma_notifica_unica_vez_con_cantidad_y_stock_restante(self):
        r = self.client.post(ROOT + 'mermas/', {'producto_id': self.producto.pk, 'cantidad': 2, 'motivo': 'DAÑO', 'observacion': 'Envase roto'}, format='json')
        self.assertEqual(r.status_code, 201, r.data); self.un_aviso_por_destinatario()
        n = self.propios().get(); self.assertIn(f'#{r.data["data"]["id"]}', n.titulo)
        self.assertIn('2 unidades', n.mensaje); self.assertIn('8 unidades', n.mensaje)

    def test_datos_invalidos_permiso_denegado_e_historial_no_generan_avisos(self):
        self.assertEqual(self.client.patch(self.url, {'precio_referencia': -1}, format='json').status_code, 400)
        self.assertEqual(self.client.post(ROOT + 'registrar-movimiento/', {'producto_id': self.producto.pk, 'tipo_movimiento': 'SALIDA', 'cantidad': 1000}, format='json').status_code, 409)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(self.url + 'eliminar-definitivamente/').status_code, 409)
        self.client.force_authenticate(self.otro); self.otro.rol = None; self.otro.save()
        self.assertEqual(self.client.patch(self.url, {'nombre': 'No permitido'}, format='json').status_code, 403)
        self.assertFalse(Notificacion.objects.exists())

    def test_fallo_de_auditoria_no_deja_notificaciones_ni_cambio(self):
        with patch('apps.productos.views.registrar_auditoria', side_effect=RuntimeError('Fallo de auditoría')):
            with self.assertLogs('django.request', level='ERROR'), self.assertRaises(RuntimeError):
                self.client.patch(self.url, {'nombre': 'No guardar'}, format='json')
        self.producto.refresh_from_db(); self.assertEqual(self.producto.nombre, 'Producto de prueba')
        self.assertFalse(Notificacion.objects.exists())

    def test_fallo_al_persistir_aviso_revierte_producto_minimo_movimiento_y_merma(self):
        operaciones = (
            lambda: self.client.patch(self.url, {'nombre': 'No guardar'}, format='json'),
            lambda: self.client.patch(self.url + 'stock-minimo/', {'bodega': self.bodega.pk, 'cantidad_minima': 5}, format='json'),
            lambda: self.client.post(ROOT + 'registrar-movimiento/', {'producto_id': self.producto.pk, 'tipo_movimiento': 'ENTRADA', 'cantidad': 5}, format='json'),
            lambda: self.client.post(ROOT + 'mermas/', {'producto_id': self.producto.pk, 'cantidad': 2, 'motivo': 'DAÑO', 'observacion': 'Envase roto'}, format='json'),
        )
        for operacion in operaciones:
            with self.subTest(operacion=operacion), patch('apps.productos.views_notificaciones.Notificacion.objects.bulk_create', side_effect=RuntimeError('Fallo de avisos')):
                with self.assertLogs('django.request', level='ERROR'), self.assertRaises(RuntimeError): operacion()
            self.stock.refresh_from_db(); self.producto.refresh_from_db()
            self.assertEqual(self.stock.cantidad_total, 10); self.assertEqual(self.producto.nombre, 'Producto de prueba')
            self.assertFalse(StockMinimo.objects.exists()); self.assertFalse(Movimiento.objects.exists()); self.assertFalse(Merma.objects.exists())
            self.assertFalse(Auditoria.objects.exists()); self.assertFalse(Notificacion.objects.exists())

    def test_operador_no_puede_notificar_creando_usuarios_sin_permiso(self):
        r = self.client.post(USUARIOS, {'email': 'no@example.com'}, format='json')
        self.assertEqual(r.status_code, 403); self.assertFalse(Notificacion.objects.exists())

    def test_crear_y_editar_usuario_notifica_solo_a_administradores(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(USUARIOS, {'email': 'avisos-nuevo@example.com', 'nombres': 'Persona', 'apellidos': 'Nueva', 'rol_id': self.rol.pk, 'password': 'Clave-Nueva-82!', 'password_confirmacion': 'Clave-Nueva-82!'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.un_aviso_por_destinatario({self.admin.pk, self.admin2.pk})
        r = self.client.patch(f'{USUARIOS}{r.data["data"]["id"]}/', {'telefono': '+56 9 1234 5678'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(list(self.propios(self.admin).values_list('titulo', flat=True)), ['Usuario creado', 'Usuario actualizado'])
        self.assertFalse(self.propios(self.actor).exists())

    def test_desactivar_reactivar_y_eliminar_usuario_sin_avisos_duplicados(self):
        self.client.force_authenticate(self.admin); ruta = f'{USUARIOS}{self.otro.pk}/'
        for _ in range(2): self.assertEqual(self.client.delete(ruta).status_code, 200)
        for _ in range(2): self.assertEqual(self.client.post(ruta + 'activar/').status_code, 200)
        self.assertEqual(self.client.delete(ruta + 'eliminar-definitivamente/').status_code, 200)
        self.assertEqual(list(self.propios(self.admin).values_list('titulo', flat=True)), ['Usuario desactivado', 'Usuario reactivado', 'Usuario eliminado'])

    def test_usuario_protegido_y_error_de_campos_no_generan_avisos(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f'{USUARIOS}{self.admin2.pk}/').status_code, 403)
        self.assertEqual(self.client.patch(f'{USUARIOS}{self.otro.pk}/', {'nombres': ''}, format='json').status_code, 400)
        self.assertFalse(Notificacion.objects.exists())

    def test_fallo_de_aviso_revierte_edicion_y_desactivacion_de_usuario(self):
        self.client.force_authenticate(self.admin); ruta = f'{USUARIOS}{self.otro.pk}/'
        for operacion in (lambda: self.client.patch(ruta, {'nombres': 'No guardar'}, format='json'), lambda: self.client.delete(ruta)):
            with self.subTest(operacion=operacion), patch('apps.productos.views_notificaciones.Notificacion.objects.bulk_create', side_effect=RuntimeError('Fallo de avisos')):
                with self.assertLogs('django.request', level='ERROR'), self.assertRaises(RuntimeError): operacion()
            self.otro.refresh_from_db(); self.assertEqual(self.otro.nombres, 'Encargado'); self.assertTrue(self.otro.activo)
            self.assertFalse(Auditoria.objects.exists()); self.assertFalse(Notificacion.objects.exists())
