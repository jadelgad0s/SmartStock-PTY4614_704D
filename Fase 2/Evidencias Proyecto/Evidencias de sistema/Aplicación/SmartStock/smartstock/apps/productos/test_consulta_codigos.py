"""Autocompletado sin duplicados, fugas de credenciales ni cambios de stock."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from threading import Barrier
from unittest import skipUnless
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.usuarios.models import Permiso, Rol, Usuario
from .consulta_codigos import reservar_consulta
from .models import (
    CodigoBarra, CupoConsultaExterna, FichaProductoExterna, Movimiento,
    Notificacion, Producto, StockBodega, StockMinimo,
)

ROOT = '/api/v1/productos/'
URL = ROOT + 'consultar-codigo/'
GTIN = '3017620422003'
CANONICO = '0' + GTIN


def ficha_publica(**extra):
    return {'status': 'success', 'product': {
        'code': GTIN, 'product_name': 'Hazelnut spread',
        'product_name_es': 'Crema de avellanas', 'generic_name_es': 'Crema para untar',
        'brands': 'Ejemplo', 'quantity': '350 g',
        'image_front_small_url': 'https://images.openfoodfacts.org/images/products/301/762/042/2003/front_es.200.jpg',
        'precio_referencia': 99999, 'stock_actual': 200, **extra,
    }}


class ConsultaCodigosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        rol = Rol.objects.create(nombre='Catálogo', codigo='encargado_bodega')
        rol.permisos.add(Permiso.objects.create(codigo='crear_producto', nombre='Crear', modulo='productos'))
        rol.permisos.add(Permiso.objects.create(codigo='editar_producto', nombre='Editar', modulo='productos'))
        cls.usuario = Usuario.objects.create_user(email='codigos@example.com', nombres='Prueba', apellidos='Catálogo', rol=rol)
        cls.lector = Usuario.objects.create_user(email='lector-codigos@example.com', nombres='Solo', apellidos='Lectura')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)
        self.parche = patch('apps.productos.consulta_codigos.build_opener')
        self.abridor = self.parche.start()
        self.addCleanup(self.parche.stop)
        self.responder(ficha_publica())

    def responder(self, payload):
        self.respuesta = MagicMock()
        self.respuesta.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        self.abridor.return_value.open.side_effect = None
        self.abridor.return_value.open.return_value = self.respuesta

    def consultar(self, codigo=GTIN):
        respuesta = self.client.get(URL, {'codigo': codigo})
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        return respuesta.data['data']

    def test_requiere_sesion_permiso_crear_y_usuario_activo(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(URL, {'codigo': GTIN}).status_code, 401)
        self.client.force_authenticate(self.lector)
        self.assertEqual(self.client.get(URL, {'codigo': GTIN}).status_code, 403)
        self.usuario.activo = False
        self.client.force_authenticate(self.usuario)
        self.assertEqual(self.client.get(URL, {'codigo': GTIN}).status_code, 403)
        self.abridor.assert_not_called()

    def test_superusuario_puede_consultar_sin_rol(self):
        admin = Usuario.objects.create_superuser(email='codigos-admin@example.com', password='prueba-aislada', nombres='Admin', apellidos='Prueba')
        self.client.force_authenticate(admin)
        self.assertEqual(self.consultar()['estado'], 'externo')

    def test_consulta_rechaza_vacio_longitud_y_caracteres_de_control(self):
        for datos in ({}, {'codigo': ''}, {'codigo': 'X' * 101}, {'codigo': 'AB\x01CD'}):
            with self.subTest(datos=datos):
                self.assertEqual(self.client.get(URL, datos).status_code, 400)
        self.abridor.assert_not_called()

    def test_busca_primero_barra_local_incluso_si_producto_esta_inactivo(self):
        p = Producto.objects.create(sku='FER-1', nombre='Producto local', activo=False)
        CodigoBarra.objects.create(producto=p, codigo=GTIN)
        datos = self.consultar()
        self.assertEqual(datos['estado'], 'existente')
        self.assertEqual(datos['producto'], {'id': p.pk, 'sku': p.sku, 'nombre': p.nombre, 'activo': False})
        self.abridor.assert_not_called()
        self.assertFalse(CupoConsultaExterna.objects.exists())

    def test_sku_y_qr_interno_se_resuelven_por_coincidencia_exacta(self):
        p = Producto.objects.create(sku='FER-UNO', nombre='Martillo')
        for codigo in ('fer-uno', 'https://smartstockchile.cl/productos/?q=FER-UNO', 'http://127.0.0.1:8000/productos/?sku=FER-UNO'):
            with self.subTest(codigo=codigo):
                self.assertEqual(self.consultar(codigo)['producto']['id'], p.pk)
        self.assertEqual(self.consultar('FER')['estado'], 'no_compatible')
        self.abridor.assert_not_called()

    def test_qr_registrado_con_url_arbitraria_se_resuelve_localmente(self):
        p = Producto.objects.create(sku='QR-LOCAL', nombre='Cable')
        codigo = 'https://proveedor.example/ficha?id=20'
        CodigoBarra.objects.create(producto=p, codigo=codigo, tipo='QR')
        self.assertEqual(self.consultar(codigo)['producto']['id'], p.pk)
        self.abridor.assert_not_called()

    def test_barra_detecta_qr_gs1_antiguo_sin_ficha_externa(self):
        p = Producto.objects.create(sku='QR-GS1', nombre='Producto con QR antiguo')
        CodigoBarra.objects.create(producto=p, tipo='QR', codigo='https://marca.example/01/' + CANONICO + '/10/LOTE')
        self.assertEqual(self.consultar()['producto']['id'], p.pk)
        self.abridor.assert_not_called()

    def test_qr_detecta_gtin_guardado_como_sku_sin_codigo_asociado(self):
        p = Producto.objects.create(sku=GTIN, nombre='Producto antiguo')
        self.assertEqual(self.consultar('https://marca.example/01/' + CANONICO)['producto']['id'], p.pk)
        self.abridor.assert_not_called()

    def test_gtin_con_ceros_y_qr_gs1_resuelven_el_mismo_producto_local(self):
        p = Producto.objects.create(sku='BEB-1', nombre='Bebida')
        CodigoBarra.objects.create(producto=p, codigo=GTIN)
        for codigo in (CANONICO, 'https://marca.example/p/01/' + CANONICO + '/10/LOTE'):
            with self.subTest(codigo=codigo):
                self.assertEqual(self.consultar(codigo)['producto']['id'], p.pk)
        self.abridor.assert_not_called()

    def test_ean8_y_upca_se_buscan_con_ceros_de_relleno_sin_perder_identidad(self):
        for indice, codigo in enumerate(('12345670', '036000291452')):
            with self.subTest(codigo=codigo):
                p = Producto.objects.create(sku='CEROS-' + str(indice), nombre='Código comercial')
                CodigoBarra.objects.create(producto=p, codigo=codigo)
                self.assertEqual(self.consultar(codigo.zfill(14))['producto']['id'], p.pk)
        self.abridor.assert_not_called()

    def test_colision_sku_y_barra_devuelve_conflicto_sin_elegir_un_producto(self):
        Producto.objects.create(sku=GTIN, nombre='Uno')
        otro = Producto.objects.create(sku='OTRO', nombre='Dos')
        CodigoBarra.objects.create(producto=otro, codigo=GTIN)
        self.assertEqual(self.client.get(URL, {'codigo': GTIN}).status_code, 409)
        self.abridor.assert_not_called()

    def test_qr_arbitrario_invalidos_y_url_local_nunca_se_visitan(self):
        for codigo in ('https://127.0.0.1/secreto', 'file:///etc/passwd', 'http://169.254.169.254/',
                       'https://marca.example/01/00000000000000', '3017620422004', '00000000',
                       'https://usuario:clave@marca.example/01/' + CANONICO):
            with self.subTest(codigo=codigo):
                self.assertEqual(self.consultar(codigo)['estado'], 'no_compatible')
        self.abridor.assert_not_called()

    def test_autocompleta_nombre_espanol_y_descripcion_sin_importar_precio_o_stock(self):
        datos = self.consultar()
        self.assertEqual(datos['estado'], 'externo')
        self.assertEqual(datos['sugerencia']['nombre'], 'Crema de avellanas 350 g')
        self.assertIn('Marca: Ejemplo', datos['sugerencia']['descripcion'])
        self.assertIn('Contenido: 350 g', datos['sugerencia']['descripcion'])
        self.assertEqual(datos['fuente']['nombre'], 'Open Food Facts')
        self.assertEqual(datos['fuente']['licencia'], 'ODbL')
        self.assertNotIn('precio_referencia', datos['sugerencia'])
        self.assertNotIn('stock_actual', datos['sugerencia'])
        for modelo in (Producto, CodigoBarra, StockBodega, StockMinimo, Movimiento, Auditoria, Notificacion):
            self.assertEqual(modelo.objects.count(), 0)

    def test_peticion_externa_tiene_identificacion_timeout_y_campos_acotados_sin_jwt(self):
        self.consultar()
        args, kwargs = self.abridor.return_value.open.call_args
        req = args[0]
        self.assertTrue(req.full_url.startswith('https://world.openfoodfacts.org/api/v3.6/product/' + GTIN + '.json?'))
        self.assertIn('product_name_es', req.full_url)
        self.assertIn('lc=es', req.full_url)
        self.assertEqual(kwargs['timeout'], 4)
        self.assertIn('SmartStock', req.get_header('User-agent'))
        self.assertIsNone(req.get_header('Authorization'))

    def test_qr_gs1_consulta_solo_gtin_a_off_y_no_la_url_del_qr(self):
        qr = 'https://marca.example/01/' + CANONICO
        self.assertEqual(self.consultar(qr)['estado'], 'externo')
        req = self.abridor.return_value.open.call_args.args[0]
        self.assertNotIn('marca.example', req.full_url)

    def test_cache_persistente_reutiliza_sugerencia_entre_lecturas_equivalentes(self):
        primero = self.consultar()
        segundo = self.consultar(CANONICO)
        self.assertEqual(primero['ficha_externa_id'], segundo['ficha_externa_id'])
        self.assertEqual(self.abridor.return_value.open.call_count, 1)
        self.assertEqual(len(CupoConsultaExterna.objects.get().intentos), 1)

    def test_cache_vencida_se_actualiza(self):
        antes = self.consultar()
        FichaProductoExterna.objects.update(vence=timezone.now() - timedelta(seconds=1))
        self.responder(ficha_publica(product_name_es='Nombre actualizado'))
        despues = self.consultar()
        self.assertEqual(antes['ficha_externa_id'], despues['ficha_externa_id'])
        self.assertEqual(despues['sugerencia']['nombre'], 'Nombre actualizado 350 g')
        self.assertEqual(self.abridor.return_value.open.call_count, 2)

    def test_404_se_guarda_temporalmente_como_sin_resultados(self):
        self.abridor.return_value.open.side_effect = HTTPError('https://world.openfoodfacts.org', 404, 'No existe', {}, BytesIO())
        self.assertEqual(self.consultar()['estado'], 'no_encontrado')
        self.assertEqual(self.consultar()['estado'], 'no_encontrado')
        self.assertEqual(self.abridor.return_value.open.call_count, 1)
        self.assertEqual(FichaProductoExterna.objects.get().datos, {})

    def test_producto_sin_nombre_permite_ingreso_manual(self):
        self.responder(ficha_publica(product_name='', product_name_es=''))
        self.assertEqual(self.consultar()['estado'], 'no_encontrado')

    def test_nombre_largo_se_acota_y_html_no_se_importa(self):
        self.responder(ficha_publica(product_name_es='<b>Nombre</b> ' + 'N' * 250, generic_name_es='<script>mal()</script> Texto', brands='<b>Marca</b>', image_front_small_url='http://127.0.0.1/imagen'))
        datos = self.consultar()['sugerencia']
        self.assertEqual(len(datos['nombre']), 200)
        self.assertNotIn('<', datos['nombre'] + datos['descripcion'])
        self.assertEqual(datos['imagen_url'], '')

    def test_no_repite_presentacion_que_ya_esta_en_el_nombre(self):
        self.responder(ficha_publica(product_name_es='Crema 350g'))
        self.assertEqual(self.consultar()['sugerencia']['nombre'], 'Crema 350g')

    def test_prefiere_imagen_seleccionada_en_espanol_segun_esquema_del_proveedor(self):
        url = 'https://images.openfoodfacts.org/images/products/301/762/042/2003/front_es.8.200.jpg'
        self.responder(ficha_publica(selected_images={'front': {'small': {'en': 'javascript:alert(1)', 'es': url}}}))
        self.assertEqual(self.consultar()['sugerencia']['imagen_url'], url)

    def test_tiempos_de_espera_red_y_json_invalido_permiten_ingreso_manual(self):
        for error in (TimeoutError('Timeout'), URLError('Sin red'), OSError('Red')):
            with self.subTest(error=type(error).__name__):
                self.abridor.return_value.open.side_effect = error
                self.assertEqual(self.consultar()['estado'], 'indisponible')
        self.abridor.return_value.open.side_effect = None
        for cuerpo in (b'No JSON', b'[]', b'X' * 65537):
            with self.subTest(cuerpo=cuerpo[:8]):
                self.respuesta.__enter__.return_value.read.return_value = cuerpo
                self.assertEqual(self.consultar()['estado'], 'indisponible')
        self.assertFalse(FichaProductoExterna.objects.exists())

    def test_no_se_acepta_ficha_de_otro_gtin(self):
        self.responder(ficha_publica(code='5449000000996'))
        self.assertEqual(self.consultar()['estado'], 'indisponible')
        self.assertFalse(FichaProductoExterna.objects.exists())

    def test_errores_http_y_redirecciones_no_se_siguen_ni_cachean(self):
        for estado in (301, 302, 403, 500, 503):
            with self.subTest(estado=estado):
                self.abridor.return_value.open.side_effect = HTTPError('https://world.openfoodfacts.org', estado, 'Error', {}, BytesIO())
                self.assertEqual(self.consultar()['estado'], 'indisponible')
        self.assertFalse(FichaProductoExterna.objects.exists())

    def test_429_respeta_retry_after_y_pausa_consultas_compartidas(self):
        self.abridor.return_value.open.side_effect = HTTPError('https://world.openfoodfacts.org', 429, 'Espera', {'Retry-After': '120'}, BytesIO())
        self.assertEqual(self.consultar()['reintentar_en'], 120)
        self.assertEqual(self.consultar('5449000000996')['estado'], 'limite')
        self.assertEqual(self.abridor.return_value.open.call_count, 1)

    def test_cupo_compartido_limita_lecturas_y_se_libera_pasado_un_minuto(self):
        for _ in range(12):
            self.assertEqual(reservar_consulta(), 0)
        datos = self.consultar()
        self.assertEqual(datos['estado'], 'limite')
        self.assertGreater(datos['reintentar_en'], 0)
        self.abridor.assert_not_called()
        CupoConsultaExterna.objects.update(intentos=[timezone.now().timestamp() - 61])
        self.assertEqual(self.consultar()['estado'], 'externo')

    def test_solo_se_crea_al_guardar_y_conserva_fuente_sin_generar_stock(self):
        consulta = self.consultar()
        respuesta = self.client.post(ROOT, {
            'sku': 'INTERNO-1', 'nombre': consulta['sugerencia']['nombre'],
            'descripcion': consulta['sugerencia']['descripcion'], 'precio_referencia': '1500.00',
            'codigos_barra': [{'codigo': GTIN, 'tipo': 'BARRA', 'es_principal': True}],
            'ficha_externa_id': consulta['ficha_externa_id'],
        }, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        p = Producto.objects.get()
        self.assertEqual(p.sku, 'INTERNO-1')
        self.assertEqual(str(p.precio_referencia), '1500.00')
        self.assertEqual(p.ficha_externa_id, consulta['ficha_externa_id'])
        self.assertIn('openfoodfacts.org/product/', respuesta.data['data']['fuente_externa']['url'])
        self.assertFalse(StockBodega.objects.exists())
        self.assertFalse(StockMinimo.objects.exists())
        r = self.client.patch(ROOT + str(p.pk) + '/', {'nombre': 'Nombre revisado'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['data']['fuente_externa']['nombre'], 'Open Food Facts')

    def test_ficha_inexistente_o_sin_resultado_no_se_puede_asociar(self):
        vacia = FichaProductoExterna.objects.create(gtin=CANONICO, datos={}, vence=timezone.now())
        for identificador in (vacia.pk, vacia.pk + 1):
            respuesta = self.client.post(ROOT, {'sku': 'NO-CREAR', 'nombre': 'Prueba', 'ficha_externa_id': identificador}, format='json')
            self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Producto.objects.exists())

    def test_importacion_rechaza_ficha_de_otro_codigo_y_duplicados_ean_gtin(self):
        consulta = self.consultar()
        payload = {'sku': 'IMPORT-1', 'nombre': 'Importado', 'ficha_externa_id': consulta['ficha_externa_id'],
                   'codigos_barra': [{'codigo': '5449000000996', 'tipo': 'BARRA'}]}
        self.assertEqual(self.client.post(ROOT, payload, format='json').status_code, 400)
        payload['codigos_barra'][0]['codigo'] = GTIN
        self.assertEqual(self.client.post(ROOT, payload, format='json').status_code, 201)
        payload['sku'] = 'OTRO-SKU'
        payload['codigos_barra'][0]['codigo'] = CANONICO
        self.assertEqual(self.client.post(ROOT, payload, format='json').status_code, 400)
        self.assertEqual(Producto.objects.count(), 1)


@skipUnless(connection.vendor == 'postgresql', 'Requiere bloqueos por fila de PostgreSQL.')
class ConsultaCodigosConcurrenteTests(TransactionTestCase):
    def test_cupo_compartido_no_excede_doce_reservas_concurrentes(self):
        barrera = Barrier(4)

        def reservar(_):
            try:
                barrera.wait(timeout=10)
                return reservar_consulta() == 0
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=4) as executor:
            aceptadas = list(executor.map(reservar, range(20)))
        self.assertEqual(sum(aceptadas), 12)

    def test_dos_altas_importadas_simultaneas_crean_un_solo_producto(self):
        usuario = Usuario.objects.create_superuser(email='concurrente-codigo@example.com', password='prueba-aislada', nombres='Prueba', apellidos='Concurrencia')
        ficha = FichaProductoExterna.objects.create(gtin=CANONICO, datos={'nombre': 'Crema'}, vence=timezone.now() + timedelta(days=1))
        barrera = Barrier(2)

        def crear(indice):
            try:
                cliente = APIClient()
                cliente.force_authenticate(Usuario.objects.get(pk=usuario.pk))
                barrera.wait(timeout=10)
                return cliente.post(ROOT, {
                    'sku': 'IMPORT-' + str(indice), 'nombre': 'Crema', 'ficha_externa_id': ficha.pk,
                    'codigos_barra': [{'codigo': (GTIN, CANONICO)[indice], 'tipo': 'BARRA'}],
                }, format='json').status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            estados = sorted(executor.map(crear, (0, 1)))
        self.assertEqual(estados, [201, 400])
        self.assertEqual(Producto.objects.count(), 1)
