"""Ejecuta la suite funcional en BrowserStack Automate con BrowserStack Local.

Instala Selenium y browserstack-local. Usa SMARTSTOCK_BS_BROWSER para elegir
firefox (por defecto), chrome, edge o safari.
"""

from getpass import getpass
from io import StringIO
from os import getenv
from uuid import uuid4

from browserstack.local import Local
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings
from selenium import webdriver
from selenium.webdriver.remote.client_config import ClientConfig
from selenium.webdriver.support.ui import WebDriverWait

from . import selenium_suite


PLATAFORMAS = {
    'firefox': (webdriver.FirefoxOptions, 'Windows', '11'),
    'chrome': (webdriver.ChromeOptions, 'Windows', '11'),
    'edge': (webdriver.EdgeOptions, 'Windows', '11'),
    'safari': (webdriver.SafariOptions, 'OS X', 'Sonoma'),
}
HUB = 'https://hub.browserstack.com/wd/hub'


@override_settings(ALLOWED_HOSTS=[*settings.ALLOWED_HOSTS, 'bs-local.com'])
class SmartStockBrowserStackTests(selenium_suite.SmartStockSeleniumTests):
    modo_visible = False

    @classmethod
    def setUpClass(cls):
        cls.browser = getenv('SMARTSTOCK_BS_BROWSER', 'firefox').strip().lower()
        if cls.browser not in PLATAFORMAS:
            raise ValueError('SMARTSTOCK_BS_BROWSER debe ser firefox, chrome, edge o safari.')

        usuario = (getenv('BROWSERSTACK_USERNAME') or input('Usuario de BrowserStack: ')).strip()
        clave = (getenv('BROWSERSTACK_ACCESS_KEY') or getpass('Access Key de BrowserStack: ')).strip()
        if not usuario or not clave:
            raise ValueError('Se necesitan el usuario y la Access Key de BrowserStack Automate.')

        super().setUpClass()
        cls.identificador = 'smartstock-' + uuid4().hex[:12]
        cls.conexion_remota = ClientConfig(remote_server_addr=HUB, username=usuario, password=clave, timeout=120)
        tunel = Local()
        cls.addClassCleanup(tunel.stop)
        tunel.start(key=clave, localIdentifier=cls.identificador)

    @property
    def live_server_url(self):
        url = super().live_server_url
        if self.browser == 'safari':
            return url.replace('://localhost:', '://bs-local.com:', 1)
        return url

    def setUp(self):
        call_command('seed', sin_admin=True, stdout=StringIO())
        tipo_opciones, sistema, version_sistema = PLATAFORMAS[self.browser]
        opciones = tipo_opciones()
        opciones.browser_version = 'latest'
        opciones.set_capability('bstack:options', {
            'os': sistema,
            'osVersion': version_sistema,
            'resolution': '1920x1080',
            'local': True,
            'localIdentifier': self.identificador,
            'projectName': 'SmartStock',
            'buildName': f'Compatibilidad {self.browser} {self.identificador}',
            'sessionName': self.id().rsplit('.', 1)[-1],
        })
        self.navegador = webdriver.Remote(command_executor=HUB, options=opciones, client_config=self.conexion_remota)
        self.addCleanup(self.navegador.quit)
        self.navegador.set_page_load_timeout(60)
        self.espera = WebDriverWait(self.navegador, 30)
