"""Contrato de inicio y acceso de los tres roles que instala SmartStock."""

from io import StringIO
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.productos.models import Bodega, Producto, StockBodega, StockMinimo, Transferencia
from .models import Rol, Usuario


API = '/api/v1/productos/'
CLAVE = 'EnsayoSmartStock290!'


class InicioPorRolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed', sin_admin=True, stdout=StringIO())
        for codigo in ('administrador', 'encargado_bodega', 'operador'):
            Usuario.objects.create_user(
                email=f'{codigo}@example.com', password=CLAVE, rol=Rol.objects.get(codigo=codigo),
            )
        cls.central = Bodega.objects.create(nombre='Bodega Central')
        cls.norte = Bodega.objects.create(nombre='Bodega Norte')
        cls.producto = Producto.objects.create(nombre='Martillo de prueba', sku='MARTILLO')
        StockBodega.objects.create(producto=cls.producto, bodega=cls.central, cantidad_total=2)
        StockBodega.objects.create(producto=cls.producto, bodega=cls.norte, cantidad_total=10)
        StockMinimo.objects.create(producto=cls.producto, bodega=cls.central, cantidad_minima=4)

    def iniciar(self, rol, web=False):
        cliente = APIClient(enforce_csrf_checks=web)
        url = '/api/v1/auth/login/'
        cabeceras = {}
        if web:
            cliente.get('/')
            cabeceras['HTTP_X_CSRFTOKEN'] = cliente.cookies['csrftoken'].value
            url = '/api/v1/auth/login-web/'
        r = cliente.post(url, {'email': f'{rol}@example.com', 'password': CLAVE},
                         format='json', **cabeceras)
        self.assertEqual(r.status_code, 200)
        sesion = r.data['data']
        cliente.credentials(HTTP_AUTHORIZATION='Bearer ' + sesion['access'])
        return cliente, sesion

    def test_urls_web_restringen_los_modulos_antes_de_renderizar(self):
        comunes = {'/productos/', '/bodegas/', '/ubicaciones/', '/movimientos/'}
        supervisor = {'/inicio-bodega/', '/transferencias/', '/mermas/', '/reportes/'}
        administrador = {'/dashboard/', '/auditoria/', '/usuarios/', '/alertas-sms/'}
        protegidas = comunes | supervisor | administrador
        anonimo = APIClient()
        for ruta in protegidas:
            self.assertRedirects(anonimo.get(ruta), '/', fetch_redirect_response=False)
        self.assertEqual(anonimo.get('/contacto/').status_code, 200)

        for rol, permitidas in (
            ('administrador', protegidas),
            ('encargado_bodega', comunes | supervisor),
            ('operador', comunes),
        ):
            cliente, sesion = self.iniciar(rol, web=True)
            self.assertEqual(set(cliente.get('/api/v1/auth/navegacion/').data['data']['modulos']), permitidas)
            for ruta in protegidas:
                with self.subTest(rol=rol, ruta=ruta):
                    respuesta = cliente.get(ruta)
                    self.assertIn('no-store', respuesta['Cache-Control'])
                    if ruta in permitidas:
                        self.assertEqual(respuesta.status_code, 200)
                    else:
                        self.assertRedirects(respuesta, sesion['inicio'], fetch_redirect_response=False)

    def test_login_web_exige_csrf_y_logout_invalida_sesion_y_refresh(self):
        cliente = APIClient(enforce_csrf_checks=True)
        datos = {'email': 'operador@example.com', 'password': CLAVE}
        self.assertEqual(cliente.post('/api/v1/auth/login-web/', datos, format='json').status_code, 403)

        cliente, sesion = self.iniciar('operador', web=True)
        self.assertEqual(cliente.get('/cerrar-sesion/').status_code, 405)
        self.assertEqual(cliente.post('/cerrar-sesion/').status_code, 403)
        r = cliente.post('/cerrar-sesion/', {'refresh': sesion['refresh']},
                         HTTP_X_CSRFTOKEN=cliente.cookies['csrftoken'].value)
        self.assertRedirects(r, '/', fetch_redirect_response=False)
        self.assertRedirects(cliente.get('/movimientos/'), '/', fetch_redirect_response=False)
        self.assertEqual(cliente.post('/api/v1/auth/refresh/', {'refresh': sesion['refresh']},
                                      format='json').status_code, 401)

    def test_staff_operativo_no_accede_a_django_admin(self):
        for rol in ('operador', 'encargado_bodega', 'administrador'):
            Usuario.objects.filter(email=f'{rol}@example.com').update(is_staff=True)
            cliente, _ = self.iniciar(rol, web=True)
            with self.subTest(rol=rol):
                respuesta = cliente.get('/admin/')
                modulos = cliente.get('/api/v1/auth/navegacion/').data['data']['modulos']
                if rol == 'administrador':
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertIn('/admin/', modulos)
                else:
                    self.assertRedirects(respuesta, '/admin/login/?next=/admin/', fetch_redirect_response=False)
                    self.assertNotIn('/admin/', modulos)
                    r = APIClient().post('/admin/login/', {
                        'username': f'{rol}@example.com', 'password': CLAVE, 'next': '/admin/',
                    })
                    self.assertEqual(r.status_code, 200)
                    self.assertTrue(r.context['form'].errors)

    def test_rol_inactivo_bloquea_token_emitido_y_sesion_web(self):
        cliente, sesion = self.iniciar('operador', web=True)
        Rol.objects.filter(codigo='operador').update(activo=False)
        self.assertRedirects(cliente.get('/movimientos/'), '/', fetch_redirect_response=False)
        self.assertEqual(cliente.get(API).status_code, 403)
        self.assertEqual(cliente.get(API + 'notificaciones/no-leidas/').status_code, 403)
        self.assertEqual(cliente.post('/api/v1/auth/refresh/', {'refresh': sesion['refresh']},
                                      format='json').status_code, 401)
        self.assertEqual(cliente.post('/api/v1/auth/login/', {
            'email': 'operador@example.com', 'password': CLAVE,
        }, format='json').status_code, 401)

    def test_revocar_permiso_de_consulta_ajusta_menu_url_y_api(self):
        cliente, _ = self.iniciar('operador', web=True)
        rol = Rol.objects.get(codigo='operador')
        rol.permisos.remove(rol.permisos.get(codigo='ver_movimiento'))
        nav = cliente.get('/api/v1/auth/navegacion/').data['data']
        self.assertEqual(nav['inicio'], '/productos/')
        self.assertNotIn('/movimientos/', nav['modulos'])
        self.assertRedirects(cliente.get('/movimientos/'), '/productos/', fetch_redirect_response=False)
        self.assertEqual(cliente.get(API + 'movimientos/').status_code, 403)

    def test_operador_registra_movimientos_pero_no_altera_catalogo_o_transferencias(self):
        operador, _ = self.iniciar('operador')
        encargado, _ = self.iniciar('encargado_bodega')
        stock = StockBodega.objects.get(producto=self.producto, bodega=self.central)
        traslado = {
            'bodega_origen_id': self.central.pk, 'bodega_destino_id': self.norte.pk,
            'producto_id': self.producto.pk, 'cantidad': 1, 'solicitud_id': str(uuid4()),
        }
        self.assertEqual(operador.post(API + 'transferencias/', traslado, format='json').status_code, 403)
        self.assertFalse(Transferencia.objects.exists())
        stock.refresh_from_db()
        self.assertEqual(stock.cantidad_total, 2)

        self.assertEqual(operador.patch(f'{API}{self.producto.pk}/', {'nombre': 'Otro'},
                                        format='json').status_code, 403)
        self.assertEqual(operador.post('/api/v1/bodegas/', {'nombre': 'Otra'}, format='json').status_code, 403)
        self.assertEqual(operador.get('/api/v1/auditoria/historial/').status_code, 403)
        self.assertEqual(operador.get('/api/v1/usuarios/').status_code, 403)
        self.assertEqual(operador.get('/api/v1/alertas-sms/historial/').status_code, 403)
        self.assertEqual(operador.get('/api/v1/ubicaciones/pasillos/', {'bodega': self.central.pk}).status_code, 200)
        self.assertEqual(operador.post('/api/v1/ubicaciones/pasillos/?bodega=' + str(self.central.pk),
                                       {'codigo': 'P-1'}, format='json').status_code, 403)
        for tipo in ('ENTRADA', 'SALIDA'):
            r = operador.post(API + 'registrar-movimiento/', {
                'bodega_id': self.central.pk, 'producto_id': self.producto.pk,
                'tipo_movimiento': tipo, 'cantidad': 1,
            }, format='json')
            self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(encargado.post(API + 'transferencias/', traslado, format='json').status_code, 201)
        stock.refresh_from_db()
        self.assertEqual(stock.cantidad_total, 1)

    def test_encargado_consulta_reportes_pero_no_exporta(self):
        encargado, _ = self.iniciar('encargado_bodega')
        filtros = {'informe': 'existencias', 'bodega': self.central.pk}
        self.assertEqual(encargado.get('/api/v1/reportes/consulta/', filtros).status_code, 200)
        self.assertEqual(encargado.get('/api/v1/reportes/exportar/', filtros).status_code, 403)
        self.assertEqual(encargado.get('/api/v1/reportes/imprimir/', filtros).status_code, 403)
        self.assertEqual(encargado.get('/api/v1/usuarios/').status_code, 403)

    def test_login_menu_y_acceso_a_datos_por_rol(self):
        expectativas = (
            ('administrador', '/dashboard/', 200, 200, 200),
            ('encargado_bodega', '/inicio-bodega/', 403, 200, 200),
            ('operador', '/movimientos/', 403, 403, 403),
        )
        for rol, inicio, dashboard, bodega, transferencias in expectativas:
            with self.subTest(rol=rol):
                cliente, sesion = self.iniciar(rol)
                self.assertEqual(sesion['inicio'], inicio)
                r = cliente.get('/api/v1/auth/navegacion/')
                self.assertIn('no-store', r['Cache-Control'])
                nav = r.data['data']
                self.assertEqual(nav['inicio'], inicio)
                self.assertIn(inicio, nav['modulos'])
                for ruta, endpoint, codigo in (
                    ('/dashboard/', 'dashboard-resumen/', dashboard),
                    ('/dashboard/', 'dashboard-alertas/', dashboard),
                    ('/inicio-bodega/', 'inicio-bodega/', bodega),
                    ('/transferencias/', 'transferencias/', transferencias),
                ):
                    self.assertEqual(cliente.get(API + endpoint).status_code, codigo)
                    self.assertEqual(ruta in nav['modulos'], codigo == 200)
                if rol != 'administrador':
                    self.assertTrue({'/usuarios/', '/auditoria/', '/alertas-sms/'}.isdisjoint(nav['modulos']))
                if rol == 'operador':
                    self.assertEqual(cliente.post(API + 'transferencias/', {}, format='json').status_code, 403)
                    self.assertNotIn('/reportes/', nav['modulos'])
                    self.assertNotIn('/mermas/', nav['modulos'])

    def test_inicio_bodega_filtra_el_stock_y_excluye_bodegas_inactivas(self):
        cliente, _ = self.iniciar('encargado_bodega')
        cerrada = Bodega.objects.create(nombre='Bodega cerrada', activa=False)
        central = cliente.get(API + 'inicio-bodega/').data['data']
        self.assertEqual(central['conteos'], {'bajo': 1, 'agotado': 0})
        self.assertEqual(central['alertas'][0]['stock'], 2)
        self.assertNotIn(cerrada.pk, [b['id'] for b in central['bodegas']])
        norte = cliente.get(API + 'inicio-bodega/', {'bodega': self.norte.pk}).data['data']
        self.assertEqual(norte['alertas'], [])
        self.assertEqual(cliente.get(API + 'inicio-bodega/', {'bodega': cerrada.pk}).status_code, 400)

    def test_cambiar_rol_actualiza_menu_y_api_con_el_mismo_token(self):
        cliente, _ = self.iniciar('administrador')
        Usuario.objects.filter(email='administrador@example.com').update(rol=Rol.objects.get(codigo='operador'))
        nav = cliente.get('/api/v1/auth/navegacion/').data['data']
        self.assertEqual(nav['inicio'], '/movimientos/')
        self.assertNotIn('/dashboard/', nav['modulos'])
        self.assertEqual(cliente.get(API + 'dashboard-resumen/').status_code, 403)
