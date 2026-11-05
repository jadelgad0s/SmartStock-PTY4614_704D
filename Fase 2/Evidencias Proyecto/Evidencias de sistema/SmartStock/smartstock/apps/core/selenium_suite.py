"""Pruebas web de SmartStock con Chrome y una base de datos de prueba SQLite.

Ejecutar con Selenium instalado y los ajustes aislados de Django:
python manage.py test apps.core.selenium_suite --settings=config.settings.testing

Define SMARTSTOCK_SELENIUM_VISIBLE=1 para abrir Chrome y ver las acciones.
"""

from io import StringIO
from os import getenv
from time import sleep

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from apps.productos.models import Bodega, DetalleMovimiento, Movimiento, Producto, StockBodega
from apps.usuarios.models import Rol, Usuario


if (settings.SETTINGS_MODULE != 'config.settings.testing'
        or settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3'
        or settings.DATABASES['default']['NAME'] != ':memory:'):
    raise RuntimeError('Ejecuta Selenium con config.settings.testing y SS_TEST_POSTGRES desactivado.')


class SmartStockSeleniumTests(StaticLiveServerTestCase):
    clave = 'Solo-Pruebas-Selenium-42!'

    def setUp(self):
        call_command('seed', sin_admin=True, stdout=StringIO())
        self.modo_visible = getenv('SMARTSTOCK_SELENIUM_VISIBLE') == '1'
        opciones = webdriver.ChromeOptions()
        if not self.modo_visible:
            opciones.add_argument('--headless=new')
        opciones.add_argument('--window-size=1440,1000')
        self.navegador = webdriver.Chrome(options=opciones)
        self.addCleanup(self.navegador.quit)
        self.addCleanup(self.pausa_demostracion)
        self.navegador.set_page_load_timeout(30)
        self.espera = WebDriverWait(self.navegador, 15)

    def pausa_demostracion(self):
        if self.modo_visible:
            sleep(2)

    def iniciar_sesion(self, codigo_rol, clave_incorrecta=False):
        usuario = Usuario.objects.create_user(
            email=f'{codigo_rol}@selenium.test', password=self.clave,
            nombres='Cuenta', apellidos='de prueba', rol=Rol.objects.get(codigo=codigo_rol),
        )
        self.navegador.get(self.live_server_url + '/')
        self.navegador.find_element(By.ID, 'email').send_keys(usuario.email)
        self.navegador.find_element(By.ID, 'password').send_keys(
            'Contraseña incorrecta' if clave_incorrecta else self.clave,
        )
        self.clic('login-submit')
        return usuario

    def clic(self, control):
        self.pausa_demostracion()
        self.espera.until(EC.element_to_be_clickable((By.ID, control))).click()

    def esperar_modulo(self, ruta):
        self.espera.until(EC.url_to_be(self.live_server_url + ruta))
        self.espera.until(EC.visibility_of_element_located((
            By.CSS_SELECTOR, '.ss-app-layout[data-ss-autorizado]',
        )))
        self.pausa_demostracion()

    def preparar_stock(self):
        producto = Producto.objects.create(sku='BEB-TEST', nombre='Bebida de prueba')
        bodega = Bodega.objects.create(nombre='Bodega Selenium')
        return StockBodega.objects.create(producto=producto, bodega=bodega, cantidad_total=10)

    def abrir_movimiento(self, sku, tipo, cantidad):
        escaner = self.espera.until(EC.element_to_be_clickable((By.ID, 'inputEscaner')))
        escaner.send_keys(sku, Keys.ENTER)
        self.espera.until(EC.visibility_of_element_located((By.ID, 'modalAccionMovimiento')))
        self.assertEqual(self.navegador.find_element(By.ID, 'movSkuProducto').text, f'SKU: {sku}')
        Select(self.navegador.find_element(By.ID, 'movTipo')).select_by_value(tipo)
        campo = self.navegador.find_element(By.ID, 'movCantidad')
        campo.clear()
        campo.send_keys(str(cantidad))

    def test_administrador_ingresa_al_dashboard_y_cierra_sesion(self):
        self.iniciar_sesion('administrador')
        self.esperar_modulo('/dashboard/')
        self.clic('btn-logout')
        self.espera.until(EC.url_to_be(self.live_server_url + '/'))
        self.navegador.get(self.live_server_url + '/dashboard/')
        self.espera.until(EC.visibility_of_element_located((By.ID, 'login-form')))

    def test_encargado_ingresa_al_inicio_de_bodega(self):
        self.iniciar_sesion('encargado_bodega')
        self.esperar_modulo('/inicio-bodega/')
        self.assertEqual(self.navegador.find_element(By.ID, 'tituloInicioBodega').text, 'Inicio de bodega')

    def test_operador_no_accede_a_usuarios(self):
        self.iniciar_sesion('operador')
        self.esperar_modulo('/movimientos/')
        self.assertFalse(self.navegador.find_element(By.ID, 'menu-usuarios').is_displayed())
        self.navegador.get(self.live_server_url + '/usuarios/')
        self.esperar_modulo('/movimientos/')

    def test_login_rechaza_una_contrasena_incorrecta(self):
        self.iniciar_sesion('administrador', clave_incorrecta=True)
        aviso = self.espera.until(EC.visibility_of_element_located((By.ID, 'alert-box')))
        self.assertIn('No pudimos iniciar sesión', aviso.text)
        self.assertEqual(self.navegador.current_url, self.live_server_url + '/')

    def test_catalogo_filtra_por_sku_y_limpia_la_busqueda(self):
        Producto.objects.create(sku='TAL-TEST', nombre='Taladro de prueba')
        Producto.objects.create(sku='MAR-TEST', nombre='Martillo de prueba')
        self.iniciar_sesion('administrador')
        self.esperar_modulo('/dashboard/')
        self.navegador.get(self.live_server_url + '/productos/')
        self.esperar_modulo('/productos/')
        self.espera.until(EC.text_to_be_present_in_element((By.ID, 'totalProductos'), '2 productos en total'))
        self.navegador.find_element(By.ID, 'buscadorProductos').send_keys('TAL-TEST')
        self.espera.until(EC.text_to_be_present_in_element((By.ID, 'totalProductos'), '1 resultados'))
        celdas_sku = self.navegador.find_elements(By.CSS_SELECTOR, '#listaProductos .ss-product-sku')
        self.assertEqual([celda.text for celda in celdas_sku], ['TAL-TEST'])
        self.clic('limpiarFiltrosProductos')
        self.espera.until(EC.text_to_be_present_in_element((By.ID, 'totalProductos'), '2 productos en total'))
        self.assertEqual(self.navegador.find_element(By.ID, 'buscadorProductos').get_property('value'), '')

    def test_entrada_y_salida_actualizan_stock_e_historial(self):
        stock = self.preparar_stock()
        usuario = self.iniciar_sesion('operador')
        self.esperar_modulo('/movimientos/')

        for tipo, cantidad, saldo, signo in (('ENTRADA', 24, 34, '+'), ('SALIDA', 3, 31, '−')):
            with self.subTest(tipo=tipo):
                self.abrir_movimiento(stock.producto.sku, tipo, cantidad)
                self.espera.until(EC.text_to_be_present_in_element((By.ID, 'movResumenConfirmacion'), f'{saldo} unidades'))
                self.clic('confirmarMovimiento')
                self.espera.until(EC.invisibility_of_element_located((By.ID, 'modalAccionMovimiento')))
                self.espera.until(EC.text_to_be_present_in_element((By.ID, 'listaMovimientos'), f'{signo}{cantidad}'))
                stock.refresh_from_db()
                self.assertEqual(stock.cantidad_total, saldo)
                self.pausa_demostracion()

        movimientos = DetalleMovimiento.objects.filter(
            producto=stock.producto, movimiento__usuario=usuario, movimiento__bodega=stock.bodega,
        ).order_by('pk').values_list('movimiento__tipo__nombre', 'cantidad')
        self.assertEqual(list(movimientos), [('ENTRADA', 24), ('SALIDA', 3)])

    def test_salida_sin_stock_suficiente_no_se_puede_confirmar(self):
        stock = self.preparar_stock()
        self.iniciar_sesion('operador')
        self.esperar_modulo('/movimientos/')
        self.abrir_movimiento(stock.producto.sku, 'SALIDA', 11)
        self.espera.until(EC.text_to_be_present_in_element((By.ID, 'movResumenConfirmacion'), 'Stock insuficiente'))
        self.assertFalse(self.navegador.find_element(By.ID, 'confirmarMovimiento').is_enabled())
        self.assertFalse(Movimiento.objects.exists())
        stock.refresh_from_db()
        self.assertEqual(stock.cantidad_total, 10)
