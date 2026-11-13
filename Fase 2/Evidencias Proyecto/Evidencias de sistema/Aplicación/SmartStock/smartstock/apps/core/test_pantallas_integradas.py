"""Smoke tests de plantillas compartidas (sin cámara física)."""
from django.test import SimpleTestCase
from django.template.loader import render_to_string


class PantallasIntegradasTests(SimpleTestCase):
    def test_contacto_es_publico_y_esta_enlazado_desde_el_login(self):
        login = self.client.get('/')
        self.assertContains(login, 'href="/contacto/"')

        contacto = self.client.get('/contacto/')
        self.assertTemplateUsed(contacto, 'usuarios/contacto.html')
        self.assertContains(contacto, 'Contacta a SmartStock')
        self.assertContains(contacto, 'href="mailto:contacto@smartstockchile.cl"')
        self.assertContains(contacto, '<a href="/" class="ss-auth-back">')

    def test_transferencias_integra_navegacion_y_confirmacion_con_prevision(self):
        for pantalla in ('dashboard.html', 'productos.html', 'bodegas.html', 'movimientos.html',
                         'transferencias.html', 'mermas.html', 'auditoria.html', 'usuarios/listar.html'):
            with self.subTest(pantalla=pantalla):
                self.assertIn('href="/transferencias/"', render_to_string(pantalla))
        html = render_to_string('transferencias.html')
        for identificador in ('transferenciaOrigen', 'transferenciaDestino', 'transferenciaProducto',
                              'transferenciaCantidad', 'stockOrigenTransferencia', 'stockDestinoTransferencia',
                              'avisoTransferenciaPendiente', 'ssModalCamara'):
            self.assertIn(f'id="{identificador}"', html)
        self.assertIn('data-target="transferenciaCodigo"', html)
        self.assertIn('aria-controls="camposFiltrosTransferencias"', html)
        self.assertIn('transferencias.js', html)

    def test_movimientos_incluye_modal_camara_y_entrada_manual(self):
        html = render_to_string('movimientos.html')
        self.assertIn('id="inputEscaner"', html)
        self.assertIn('data-target="inputEscaner"', html)
        self.assertIn('id="ssModalCamara"', html)
        self.assertIn('id="modalIngresoManual"', html)
        self.assertIn('escaneo_camara.js', html)
        self.assertIn('id="movBodega"', html)
        self.assertIn('for="movBodega"', html)
        self.assertIn('id="reintentarStockMovimiento"', html)
        self.assertIn('js/movimientos.js?v=confirmacion-1', html)

    def test_logotipo_es_el_mismo_en_modulos(self):
        for ruta in [
            'dashboard.html', 'productos.html', 'movimientos.html',
            'auditoria.html', 'mermas.html', 'usuarios/listar.html',
        ]:
            with self.subTest(ruta=ruta):
                html = render_to_string(ruta)
                self.assertIn('branding/smartstock-mark.png', html)

    def test_lector_de_productos_mantiene_botones_de_camara(self):
        html = render_to_string('productos.html')
        self.assertIn('data-target="inputCodigoBarra"', html)
        self.assertIn('data-target="editCodigosBarra"', html)
        self.assertIn('id="ssModalCamara"', html)

    def test_campana_consulta_avisos_sin_navegar_y_muestra_alerta(self):
        from django.contrib.staticfiles import finders

        archivo = finders.find('js/notificaciones.js')
        self.assertIsNotNone(archivo)
        with open(archivo, encoding='utf-8') as fuente:
            codigo = fuente.read()

        self.assertIn("setInterval(() => { if (!document.hidden) cargar(); }, 10000)", codigo)
        self.assertIn("cache: 'no-store'", codigo)
        self.assertIn("sessionStorage.setItem(claveVistos", codigo)
        self.assertIn("new BroadcastChannel('smartstock-notificaciones')", codigo)
        self.assertIn("toast.show()", codigo)
        self.assertIn("ss-notif-just-arrived", codigo)

    def test_modulos_actualizan_campana_al_guardar_sin_banners_de_exito(self):
        from django.contrib.staticfiles import finders

        for archivo in ('js/movimientos.js', 'js/mermas.js', 'js/productos.js', 'js/usuarios_api.js'):
            with self.subTest(archivo=archivo):
                ruta = finders.find(archivo)
                self.assertIsNotNone(ruta)
                with open(ruta, encoding='utf-8') as fuente:
                    self.assertIn(
                        "new Event('smartstock:notifications-changed')",
                        fuente.read(),
                    )
        for plantilla, identificador in (
            ('productos.html', 'avisoResultadoProductos'), ('movimientos.html', 'estadoRegistroMovimiento'),
            ('mermas.html', 'avisoResultadoMerma'), ('usuarios/listar.html', 'avisoResultadoUsuarios'),
        ):
            with self.subTest(plantilla=plantilla):
                self.assertNotIn(f'id="{identificador}"', render_to_string(plantilla))

    def test_plantilla_carga_version_actualizada_de_notificaciones(self):
        html = render_to_string('base.html')
        self.assertIn('notificaciones.js', html)
        self.assertIn('js/notificaciones.js?v=roles-1', html)

    def test_login_distingue_logo_en_escritorio_y_conserva_el_mobile(self):
        html = render_to_string('login.html')
        self.assertIn('ss-login-brand-icon', html)
        self.assertIn('ss-login-form-card', html)
        self.assertIn('branding/smartstock-mark.png', html)
        self.assertIn('d-lg-none', html)
        self.assertIn('id="login-form"', html)
        self.assertIn('/recuperar-clave/', html)

    def test_login_usa_css_actualizado(self):
        from django.contrib.staticfiles import finders
        html = render_to_string('login.html')
        self.assertIn('responsive.css', html)
        self.assertIn('responsive.', html)
        ruta = finders.find('css/responsive.css')
        self.assertIsNotNone(ruta)
        with open(ruta, encoding='utf-8') as archivo:
            estilos = archivo.read()
        self.assertIn('.ss-login-brand-icon', estilos)
        self.assertIn('.ss-login-form-card', estilos)
        self.assertIn('translateY(-28px)', estilos)

    def test_sidebar_logo_usa_el_inicio_de_la_cuenta_y_el_perfil_es_visible(self):
        pantallas = (
            'dashboard.html', 'productos.html', 'movimientos.html',
            'mermas.html', 'auditoria.html', 'usuarios/listar.html',
        )
        for pantalla in pantallas:
            with self.subTest(pantalla=pantalla):
                html = render_to_string(pantalla)
                self.assertIn('href="/" data-ss-inicio aria-label="Ir al inicio de SmartStock"', html)
                self.assertIn('ss-sidebar-links', html)
                self.assertIn('ss-sidebar-profile', html)
                self.assertIn('ss-profile-card', html)

    def test_cada_modulo_tiene_control_accesible_de_tema(self):
        for pantalla in (
            'dashboard.html', 'productos.html', 'movimientos.html',
            'mermas.html', 'auditoria.html', 'usuarios/listar.html',
        ):
            with self.subTest(pantalla=pantalla):
                html = render_to_string(pantalla)
                self.assertIn('ss-theme-toggle', html)
                self.assertIn('aria-pressed="false"', html)
                self.assertIn('Activar modo oscuro', html)

    def test_tema_se_recuerda_y_no_borra_tokens_al_cerrar_sesion(self):
        from django.contrib.staticfiles import finders
        for archivo, fragmentos in {
            'js/theme.js': [
                "localStorage.setItem(KEY", "data-bs-theme",
                "smartstockClearSession", "smartstock:themechange",
            ],
            'css/theme.css': [
                'height: 100dvh', '.ss-sidebar-links',
                ':root[data-bs-theme="dark"]', '.modal-content',
                '.ss-notif-menu',
            ],
            'js/dashboard.js': ['smartstock:themechange', 'chartLineInstance'],
        }.items():
            with self.subTest(archivo=archivo):
                ruta = finders.find(archivo)
                self.assertIsNotNone(ruta)
                with open(ruta, encoding='utf-8') as contenido:
                    texto = contenido.read()
                for fragmento in fragmentos:
                    self.assertIn(fragmento, texto)
        base = render_to_string('base.html')
        self.assertIn('css/theme.css', base)
        self.assertIn('js/theme.js', base)

    def test_password_toggle_en_login_y_restablecimiento(self):
        """Los tres campos cuentan con controles accesibles sin cambiar el formulario."""
        login = render_to_string('login.html')
        restablecer = render_to_string('usuarios/nueva_clave.html', {
            'validlink': True,
            'form': {
                'non_field_errors': [],
                'new_password1': {'errors': []},
                'new_password2': {'errors': []},
            },
        })
        for html, campos in (
            (login, ('password',)),
            (restablecer, ('id_new_password1', 'id_new_password2')),
        ):
            with self.subTest(campos=campos):
                self.assertIn('css/password_visibility.css', html)
                self.assertIn('js/password_visibility.js', html)
                for campo in campos:
                    self.assertIn(f'data-password-toggle="{campo}"', html)
                    self.assertIn(f'aria-controls="{campo}"', html)
                    self.assertIn('aria-label="Mostrar contraseña"', html)
        self.assertIn('autocomplete="current-password"', login)
        self.assertIn('name="new_password1"', restablecer)
        self.assertIn('name="new_password2"', restablecer)
        self.assertIn('autocomplete="new-password"', restablecer)

    def test_password_toggle_tamano_movil_y_estado_accesible(self):
        from django.contrib.staticfiles import finders

        ruta_js = finders.find('js/password_visibility.js')
        ruta_css = finders.find('css/password_visibility.css')
        self.assertIsNotNone(ruta_js)
        self.assertIsNotNone(ruta_css)

        with open(ruta_js, encoding='utf-8') as archivo:
            contenido_js = archivo.read()
        with open(ruta_css, encoding='utf-8') as archivo:
            contenido_css = archivo.read()

        self.assertIn("campo.type = visible ? 'text' : 'password'", contenido_js)
        self.assertIn("button.setAttribute('aria-pressed'", contenido_js)
        self.assertIn("button.setAttribute('aria-label'", contenido_js)
        self.assertIn('fa-eye-slash', contenido_js)
        self.assertIn('width: 44px', contenido_css)
        self.assertIn('height: 44px', contenido_css)
        self.assertIn('padding-right: 3.5rem', contenido_css)

    def test_catalogo_tiene_ordenamiento_y_paginacion_responsive(self):
        """La misma plantilla ofrece seis órdenes y paginación en móvil/escritorio."""
        html = render_to_string('productos.html')
        self.assertIn('id="ordenarProductos"', html)
        self.assertIn('id="paginacionProductos"', html)
        self.assertIn('id="resumenPaginacionProductos"', html)
        self.assertIn('css/productos_paginacion.css', html)
        self.assertIn('js/productos.js', html)
        for valor in (
            'nombre,id', '-nombre,-id',
            'precio_referencia,id', '-precio_referencia,-id',
            'fecha_creacion,id', '-fecha_creacion,-id',
        ):
            with self.subTest(valor=valor):
                self.assertIn(f'value="{valor}"', html)

    def test_catalogo_carga_assets_sin_acoplarse_a_su_version_de_cache(self):
        from html.parser import HTMLParser
        from urllib.parse import urlsplit
        from django.templatetags.static import static

        class Recursos(HTMLParser):
            def __init__(self):
                super().__init__()
                self.scripts = []
                self.estilos = []
                self.elementos = {}

            def handle_starttag(self, tag, attrs):
                atributos = dict(attrs)
                if tag == 'script' and 'src' in atributos:
                    self.scripts.append(urlsplit(atributos['src']).path)
                if tag == 'link' and atributos.get('rel') == 'stylesheet':
                    self.estilos.append(urlsplit(atributos['href']).path)
                if 'id' in atributos:
                    self.elementos[atributos['id']] = atributos

        recursos = Recursos()
        recursos.feed(render_to_string('productos.html'))
        self.assertEqual(recursos.scripts.count(static('js/productos.js')), 1)
        self.assertIn(static('css/productos_paginacion.css'), recursos.estilos)
        self.assertEqual(recursos.elementos['totalProductos']['tabindex'], '-1')
        self.assertEqual(recursos.elementos['listaProductos']['aria-busy'], 'true')

    def test_catalogo_filtros_y_reintentos_tienen_controles_accesibles(self):
        html = render_to_string('productos.html')
        from html.parser import HTMLParser

        class Controles(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = {}
                self.etiquetas = set()

            def handle_starttag(self, tag, attrs):
                datos = dict(attrs)
                if datos.get('id'):
                    self.ids[datos['id']] = datos
                if tag == 'label' and datos.get('for'):
                    self.etiquetas.add(datos['for'])

        controles = Controles()
        controles.feed(html)
        for identificador in ('buscadorProductos', 'bodegaProductos', 'estadoProductos', 'stockProductos', 'ordenarProductos'):
            self.assertIn(identificador, controles.ids)
            self.assertIn(identificador, controles.etiquetas)
        self.assertEqual(controles.ids['mostrarFiltrosProductos']['aria-controls'], 'filtrosProductos')
        self.assertEqual(controles.ids['mostrarFiltrosProductos']['aria-expanded'], 'false')
        self.assertIn('reintentarProductos', controles.ids)
        self.assertIn('reintentarOpcionesProductos', controles.ids)

    def test_catalogo_conserva_doble_navegacion_y_control_para_volver_arriba(self):
        from html.parser import HTMLParser

        class Navegacion(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = {}

            def handle_starttag(self, tag, attrs):
                datos = dict(attrs)
                if datos.get('id'):
                    self.ids[datos['id']] = (tag, datos)

        elementos = Navegacion()
        elementos.feed(render_to_string('productos.html'))
        for identificador in ('paginacionProductosSuperior', 'paginacionProductos'):
            tag, attrs = elementos.ids[identificador]
            self.assertEqual(tag, 'nav')
            self.assertIn('aria-label', attrs)
        tag, attrs = elementos.ids['ssVolverArriba']
        self.assertEqual(tag, 'button')
        self.assertEqual(attrs['type'], 'button')
        self.assertEqual(attrs['aria-label'], 'Volver arriba')

    def test_catalogo_formularios_y_confirmacion_tienen_contexto_y_precio_decimal(self):
        from html.parser import HTMLParser

        class Elementos(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = {}

            def handle_starttag(self, tag, attrs):
                datos = dict(attrs)
                if datos.get('id'):
                    self.ids[datos['id']] = datos

        elementos = Elementos()
        elementos.feed(render_to_string('productos.html'))
        for identificador in ('inputPrecio', 'editPrecio'):
            campo = elementos.ids[identificador]
            self.assertEqual(campo['min'], '0')
            self.assertEqual(campo['step'], '0.01')
            self.assertIn(identificador + 'Error', campo['aria-describedby'])
        for identificador in ('nombreAccionProducto', 'skuAccionProducto', 'descripcionAccionProducto', 'errorAccionProducto'):
            self.assertIn(identificador, elementos.ids)
        self.assertEqual(elementos.ids['modalAccionProducto']['aria-labelledby'], 'tituloAccionProducto')
        self.assertIn('datosDetalleProducto', elementos.ids)
