"""Contrato de alertas SMS: sin llamadas reales ni consumo de saldo de Twilio."""
from datetime import datetime, timedelta, timezone as dt_timezone
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode
import uuid
import json

from django.core.management import call_command, CommandError
from django.db import close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient
from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator
from twilio.rest import Client as TwilioReal
from twilio.http.response import Response as RespuestaTwilio

from apps.core.models import Auditoria
from apps.usuarios.models import Rol, Usuario
from .alertas_sms import (
    callback_url, configuracion_sms, enviar_alerta_sms, evaluar_alerta_sms,
    mensaje_sms, procesar_pendientes_sms,
)
from .models import Bodega, EnvioAlertaSMS, EstadoStockSMS, LimiteDiarioSMS, Producto, StockBodega, StockMinimo

AJUSTES = {
    'SMS_ALERTAS_ACTIVAS': True, 'SMS_ALERTAS_DESTINATARIOS': ['+56911112222'],
    'SMS_ALERTAS_LIMITE_DIARIO': 20, 'SMS_ALERTAS_TIMEOUT': 3,
    'TWILIO_ACCOUNT_SID': 'AC' + '1' * 32, 'TWILIO_AUTH_TOKEN': 'token-simulado-para-pruebas-no-es-una-credencial',
    'TWILIO_MESSAGING_SERVICE_SID': '', 'TWILIO_FROM_NUMBER': '+15005550006',
    'TWILIO_PUBLIC_BASE_URL': 'https://smartstockchile.cl',
}
RUTA = '/api/v1/alertas-sms/'
CLIENTE = 'apps.productos.alertas_sms.Client'


@override_settings(**AJUSTES)
class AlertasSMSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(email='sms-admin@example.com', password='ClaveSeguraParaSMS123!', nombres='Admin', apellidos='SMS')
        cls.bodega = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        cls.otra = Bodega.objects.create(nombre='Bodega Sur', direccion='Sur')
        cls.producto = Producto.objects.create(sku='SMS-001', nombre='Martillo galponero')
        cls.stock = StockBodega.objects.create(producto=cls.producto, bodega=cls.bodega, cantidad_total=10)
        cls.minimo = StockMinimo.objects.create(producto=cls.producto, bodega=cls.bodega, cantidad_minima=5)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        parche = patch(CLIENTE)
        self.proveedor = parche.start()
        self.addCleanup(parche.stop)
        self.numero = 0

        def aceptar(**kwargs):
            self.numero += 1
            return SimpleNamespace(sid='SM' + f'{self.numero:032x}', status='queued', error_code=None)
        self.proveedor.return_value.messages.create.side_effect = aceptar

    def evaluar(self, cantidad=5):
        StockBodega.objects.filter(pk=self.stock.pk).update(cantidad_total=cantidad)
        evaluar_alerta_sms(self.producto, self.bodega)
        return EnvioAlertaSMS.objects.order_by('fecha_creacion', 'id').last()

    def callback(self, envio, estado='delivered', **cambios):
        datos = {'AccountSid': AJUSTES['TWILIO_ACCOUNT_SID'], 'MessageSid': envio.twilio_sid or 'SM' + '2' * 32,
                 'MessageStatus': estado, 'To': envio.destinatario, **cambios}
        firma = RequestValidator(AJUSTES['TWILIO_AUTH_TOKEN']).compute_signature(callback_url(envio.pk), datos)
        return self.client.post(callback_url(envio.pk).removeprefix(AJUSTES['TWILIO_PUBLIC_BASE_URL']),
                                urlencode(datos), content_type='application/x-www-form-urlencoded', HTTP_X_TWILIO_SIGNATURE=firma)

    def test_suficiente_no_crea_sms_y_el_minimo_es_inclusivo(self):
        self.assertIsNone(self.evaluar(6))
        envio = self.evaluar(5)
        self.assertEqual((envio.nivel, envio.cantidad, envio.minimo), (1, 5, 5))
        self.proveedor.assert_not_called()

    def test_un_bajo_y_un_agotado_por_ciclo_sin_repetir_en_reposicion_parcial(self):
        self.evaluar(5); self.evaluar(4); self.evaluar(2)
        self.assertEqual(EnvioAlertaSMS.objects.count(), 1)
        self.evaluar(0)
        self.evaluar(3)
        self.evaluar(0)
        self.assertEqual(list(EnvioAlertaSMS.objects.order_by('nivel').values_list('nivel', flat=True)), [1, 2])
        self.assertEqual(EnvioAlertaSMS.objects.get(nivel=1).estado, 'CANCELADO')

    def test_recuperacion_habilita_otro_ciclo(self):
        primero = self.evaluar(5)
        self.evaluar(6)
        segundo = self.evaluar(5)
        self.assertNotEqual(primero.ciclo, segundo.ciclo)
        self.assertEqual(EnvioAlertaSMS.objects.count(), 2)

    def test_minimo_cero_desactiva_bajo_y_conserva_aviso_de_agotado(self):
        self.minimo.cantidad_minima = 0; self.minimo.save()
        self.assertIsNone(self.evaluar(1))
        self.assertEqual(self.evaluar(0).nivel, 2)

    def test_respeta_stock_y_minimo_unicos_de_cada_bodega(self):
        StockMinimo.objects.filter(pk=self.minimo.pk).update(cantidad_minima=8)
        StockBodega.objects.create(producto=self.producto, bodega=self.otra, cantidad_total=100)
        StockMinimo.objects.create(producto=self.producto, bodega=self.otra, cantidad_minima=500)
        envio = self.evaluar(7)
        self.assertEqual((envio.cantidad, envio.minimo, envio.bodega_id), (7, 8, self.bodega.pk))

    def test_bodegas_tienen_ciclos_independientes(self):
        self.evaluar()
        StockBodega.objects.create(producto=self.producto, bodega=self.otra, cantidad_total=0)
        evaluar_alerta_sms(self.producto, self.otra)
        self.assertEqual(EstadoStockSMS.objects.count(), 2)
        self.assertEqual(EnvioAlertaSMS.objects.count(), 2)

    @override_settings(SMS_ALERTAS_ACTIVAS=False)
    def test_desactivado_no_crea_estado_ni_intenta_conectar(self):
        self.evaluar(0)
        self.assertFalse(EstadoStockSMS.objects.exists())
        self.assertFalse(EnvioAlertaSMS.objects.exists())
        self.proveedor.assert_not_called()

    def test_recuperacion_mientras_sms_pausado_tambien_rearma_el_ciclo(self):
        primero = self.evaluar()
        with override_settings(SMS_ALERTAS_ACTIVAS=False):
            self.evaluar(6)
            self.evaluar(4)
            enviar_alerta_sms(primero.pk)
        ultimo = self.evaluar(3)
        self.assertNotEqual(primero.ciclo, ultimo.ciclo)
        self.proveedor.assert_not_called()

    def test_inactivos_no_generan_y_pendientes_se_cancelan_antes_de_enviar(self):
        envio = self.evaluar()
        self.bodega.activa = False; self.bodega.save()
        enviar_alerta_sms(envio.pk)
        envio.refresh_from_db()
        self.assertEqual((envio.estado, envio.intentos), ('CANCELADO', 0))
        self.producto.activo = False; self.producto.save()
        self.evaluar(0)
        self.assertEqual(EnvioAlertaSMS.objects.count(), 1)
        self.proveedor.assert_not_called()

    def test_destinatarios_duplicados_se_deduplican(self):
        with override_settings(SMS_ALERTAS_DESTINATARIOS=['+56911112222', '+56911112222', '+56933334444']):
            self.evaluar()
        self.assertEqual(EnvioAlertaSMS.objects.count(), 2)

    def test_destinatarios_incorrectos_no_disparan_sms(self):
        for telefonos in ([], ['911112222'], ['+56911112222', '+15555555555'], ['+56911112222'] * 4 + ['+56933334444', '+56955556666', '+56977778888']):
            with self.subTest(telefonos=telefonos), override_settings(SMS_ALERTAS_DESTINATARIOS=telefonos):
                self.assertFalse(configuracion_sms()['lista'])
                self.evaluar()
        self.assertFalse(EnvioAlertaSMS.objects.exists())

    def test_configuracion_incompleta_conserva_pendiente_sin_consumir_cuota(self):
        envio = self.evaluar()
        with override_settings(TWILIO_AUTH_TOKEN=''):
            enviar_alerta_sms(envio.pk)
        envio.refresh_from_db()
        self.assertEqual((envio.estado, envio.intentos), ('PENDIENTE', 0))
        self.assertFalse(LimiteDiarioSMS.objects.exists())

    def test_rechaza_urls_credenciales_y_limites_mal_configurados(self):
        for cambios in ({'TWILIO_PUBLIC_BASE_URL': 'http://localhost'}, {'TWILIO_PUBLIC_BASE_URL': 'https://[invalida'},
                        {'TWILIO_PUBLIC_BASE_URL': 'https://host.test/ruta'}, {'TWILIO_PUBLIC_BASE_URL': 'https://u:p@host.test'},
                        {'TWILIO_ACCOUNT_SID': 'incorrecto'}, {'TWILIO_FROM_NUMBER': '123'},
                        {'TWILIO_MESSAGING_SERVICE_SID': 'incorrecto'}, {'SMS_ALERTAS_TIMEOUT': 0},
                        {'SMS_ALERTAS_TIMEOUT': 6}, {'SMS_ALERTAS_LIMITE_DIARIO': 0}):
            with self.subTest(cambios=cambios), override_settings(**cambios):
                self.assertFalse(configuracion_sms()['lista'])

    def test_mensaje_legible_con_producto_completo_singular_y_agotado(self):
        self.producto.sku = '4564774647'
        self.producto.nombre = 'Bebida Cherry Lata Coca-Cola 355 ml'
        casos = (
            (5, 1, 'stock bajo', 'Quedan 5 unidades.'),
            (1, 1, 'stock bajo', 'Queda 1 unidad.'),
            (0, 2, 'agotado', 'Quedan 0 unidades.'),
        )
        for cantidad, nivel, titulo, unidades in casos:
            with self.subTest(cantidad=cantidad):
                texto = mensaje_sms(self.producto, self.bodega, cantidad, 5, nivel)
                self.assertLessEqual(len(texto), 160)
                self.assertEqual(texto.splitlines(), [
                    f'SmartStock: {titulo}', '',
                    f'Reponer {self.producto.nombre} en {self.bodega.nombre}.',
                    f'{unidades} El minimo es 5.', '', 'SKU 4564774647', 'STOP para salir.',
                ])

    def test_texto_cabe_en_un_segmento_gsm_con_nombres_largos_y_unicode(self):
        self.producto.sku = 'S' * 50
        self.producto.nombre = 'Árbol ñandú € [prueba] {} \\ ~ ^ | \x00\x1b\n\t' * 5
        self.bodega.nombre = 'Bódega Región Ñuble muy extensa ' * 3
        for nivel in (1, 2):
            texto = mensaje_sms(self.producto, self.bodega, 2147483647, 2147483647, nivel)
            self.assertLessEqual(len(texto), 160)
            self.assertTrue(texto.isascii())
            lineas = texto.splitlines()
            self.assertEqual(len(lineas), 6)
            self.assertTrue(lineas[1].startswith('Arbol'))
            self.assertTrue(lineas[2].startswith('Bodeg'))
            self.assertTrue(lineas[1].endswith('...'))
            self.assertTrue(lineas[2].endswith('...'))
            self.assertIn('2147483647', lineas[3])
            self.assertIn('Minimo: 2147483647.', lineas[3])
            self.assertEqual(lineas[-2:], [f'SKU {self.producto.sku}', 'STOP para salir.'])
            self.assertFalse(any(c in texto for c in '[]{}\\~^|`'))

    def test_texto_con_suma_de_existencias_grande_conserva_sku_y_cantidades(self):
        self.producto.sku = 'S' * 50
        self.producto.nombre = 'Producto con un nombre muy largo ' * 6
        self.bodega.nombre = 'Bodega con un nombre muy largo ' * 3
        texto = mensaje_sms(self.producto, self.bodega, 9223372036854775807, 2147483647, 1)
        self.assertLessEqual(len(texto), 160)
        self.assertIn('Stock: 9223372036854775807. Minimo: 2147483647.', texto)
        self.assertIn(f'SKU {self.producto.sku}\nSTOP para salir.', texto)
        self.assertEqual(len(texto.splitlines()), 6)

    def test_campos_sin_caracteres_gsm_tienen_nombre_y_bodega_de_respaldo(self):
        self.producto.nombre = '📦商品'
        self.bodega.nombre = '🏬倉庫'
        texto = mensaje_sms(self.producto, self.bodega, 1, 5, 1)
        self.assertIn('\n\nReponer Producto en Bodega.\nQueda 1 unidad.', texto)
        self.assertTrue(texto.isascii())

    def test_envio_usa_remitente_callback_timeout_y_no_autoreintenta(self):
        envio = self.evaluar()
        with patch('apps.productos.alertas_sms.TwilioHttpClient') as http:
            enviar_alerta_sms(envio.pk)
        http.assert_called_once_with(timeout=3, max_retries=0)
        datos = self.proveedor.return_value.messages.create.call_args.kwargs
        self.assertEqual((datos['to'], datos['from_']), ('+56911112222', '+15005550006'))
        self.assertEqual(datos['status_callback'], callback_url(envio.pk))
        self.assertEqual(datos['validity_period'], 300)
        envio.refresh_from_db()
        self.assertEqual((envio.estado, envio.intentos), ('ACEPTADO', 1))
        self.assertEqual(datos['body'], envio.mensaje)
        self.assertIn('\n\nReponer Martillo galponero en Bodega Central.\nQuedan 5 unidades.', datos['body'])
        enviar_alerta_sms(envio.pk)
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, 1)

    def test_messaging_service_tiene_prioridad_sobre_numero_remitente(self):
        envio = self.evaluar()
        with override_settings(TWILIO_MESSAGING_SERVICE_SID='MG' + '3' * 32):
            enviar_alerta_sms(envio.pk)
        datos = self.proveedor.return_value.messages.create.call_args.kwargs
        self.assertEqual(datos['messaging_service_sid'], 'MG' + '3' * 32)
        self.assertNotIn('from_', datos)

    def test_actualiza_cantidad_pendiente_antes_del_envio(self):
        envio = self.evaluar()
        self.evaluar(2)
        enviar_alerta_sms(envio.pk)
        envio.refresh_from_db()
        self.assertEqual(envio.cantidad, 2)
        self.assertIn('Quedan 2 unidades.', envio.mensaje)

    def test_stock_recuperado_o_destinatario_retirado_cancela_sin_red(self):
        envio = self.evaluar()
        with override_settings(SMS_ALERTAS_DESTINATARIOS=['+56933334444']):
            enviar_alerta_sms(envio.pk)
        envio.refresh_from_db(); self.assertEqual(envio.estado, 'CANCELADO')
        self.evaluar(6)
        segundo = self.evaluar(5)
        StockBodega.objects.filter(pk=self.stock.pk).update(cantidad_total=10)
        enviar_alerta_sms(segundo.pk)
        segundo.refresh_from_db(); self.assertEqual(segundo.estado, 'CANCELADO')
        self.proveedor.assert_not_called()

    @override_settings(SMS_ALERTAS_LIMITE_DIARIO=1)
    def test_cuota_diaria_compartida_incluye_todos_los_destinatarios_y_cambia_de_dia(self):
        with override_settings(SMS_ALERTAS_DESTINATARIOS=['+56911112222', '+56933334444']):
            self.evaluar()
            uno, dos = list(EnvioAlertaSMS.objects.order_by('destinatario'))
            enviar_alerta_sms(uno.pk); enviar_alerta_sms(dos.pk)
            dos.refresh_from_db(); self.assertEqual((dos.estado, dos.intentos), ('PENDIENTE', 0))
            self.assertEqual(self.proveedor.return_value.messages.create.call_count, 1)
            with patch('apps.productos.alertas_sms.timezone.localdate', return_value=timezone.localdate() + timedelta(days=1)):
                enviar_alerta_sms(dos.pk)
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, 2)
        self.assertEqual(list(LimiteDiarioSMS.objects.order_by('fecha').values_list('intentos', flat=True)), [1, 1])

    def test_cuota_utiliza_el_dia_local_de_chile(self):
        envio = self.evaluar()
        with patch('django.utils.timezone.now', return_value=datetime(2026, 10, 29, 2, 30, tzinfo=dt_timezone.utc)):
            enviar_alerta_sms(envio.pk)
        self.assertEqual(LimiteDiarioSMS.objects.get().fecha.isoformat(), '2026-10-28')

    def test_429_espera_un_minuto_y_no_supera_tres_intentos(self):
        envio = self.evaluar()
        self.proveedor.return_value.messages.create.side_effect = TwilioRestException(429, '/simulada', code=20429, msg='simulado')
        enviar_alerta_sms(envio.pk)
        envio.refresh_from_db(); self.assertEqual((envio.estado, envio.intentos), ('PENDIENTE', 1))
        enviar_alerta_sms(envio.pk)
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, 1)
        for _ in range(2):
            EnvioAlertaSMS.objects.filter(pk=envio.pk).update(proximo_intento=timezone.now() - timedelta(seconds=1))
            enviar_alerta_sms(envio.pk)
        envio.refresh_from_db(); self.assertEqual((envio.estado, envio.intentos), ('RECHAZADO', 3))
        self.assertEqual(LimiteDiarioSMS.objects.get().intentos, 3)

    def test_rechazo_de_twilio_no_se_reintenta(self):
        envio = self.evaluar()
        self.proveedor.return_value.messages.create.side_effect = TwilioRestException(400, '/simulada', code=21211, msg='simulado')
        enviar_alerta_sms(envio.pk); enviar_alerta_sms(envio.pk)
        envio.refresh_from_db()
        self.assertEqual((envio.estado, envio.codigo_error, envio.intentos), ('RECHAZADO', '21211', 1))

    def test_baja_stop_no_reintenta_el_envio_rechazado(self):
        primero = self.evaluar()
        self.proveedor.return_value.messages.create.side_effect = TwilioRestException(400, '/simulada', code=21610, msg='simulado')
        enviar_alerta_sms(primero.pk)
        enviar_alerta_sms(primero.pk)
        primero.refresh_from_db()
        self.assertEqual((primero.estado, primero.codigo_error, primero.intentos), ('RECHAZADO', '21610', 1))
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, 1)

    def test_timeout_o_500_queda_incierto_sin_reenvio_ni_secretos_en_log(self):
        for error in (TimeoutError(AJUSTES['TWILIO_AUTH_TOKEN']), TwilioRestException(500, '/simulada', code=20500, msg='simulado')):
            self.evaluar(6)
            envio = self.evaluar()
            self.proveedor.return_value.messages.create.side_effect = error
            with patch('apps.productos.alertas_sms.logger') as log:
                enviar_alerta_sms(envio.pk)
                self.assertNotIn(AJUSTES['TWILIO_AUTH_TOKEN'], str(log.mock_calls))
            enviar_alerta_sms(envio.pk)
            envio.refresh_from_db(); self.assertEqual((envio.estado, envio.intentos), ('INCIERTO', 1))

    def test_callback_firmado_confirma_entrega_sin_retroceder_por_repetidos(self):
        envio = self.evaluar(); enviar_alerta_sms(envio.pk); envio.refresh_from_db()
        self.assertEqual(self.callback(envio).status_code, 204)
        self.assertEqual(self.callback(envio).status_code, 204)
        self.assertEqual(self.callback(envio, 'queued').status_code, 204)
        envio.refresh_from_db(); self.assertEqual(envio.estado, 'ENTREGADO')

    def test_callback_temprano_no_es_sobrescrito_por_la_respuesta_rest(self):
        envio = self.evaluar()
        sid = 'SM' + '2' * 32
        def entregar(**kwargs):
            self.assertEqual(self.callback(envio, MessageSid=sid).status_code, 204)
            return SimpleNamespace(sid=sid, status='queued', error_code=None)
        self.proveedor.return_value.messages.create.side_effect = entregar
        enviar_alerta_sms(envio.pk)
        envio.refresh_from_db(); self.assertEqual((envio.estado, envio.twilio_sid), ('ENTREGADO', sid))

    def test_callback_recupera_timeout_sin_otro_sms(self):
        envio = self.evaluar()
        self.proveedor.return_value.messages.create.side_effect = TimeoutError('simulado')
        with patch('apps.productos.alertas_sms.logger'):
            enviar_alerta_sms(envio.pk)
        self.assertEqual(self.callback(envio, 'sent').status_code, 204)
        envio.refresh_from_db(); self.assertEqual(envio.estado, 'ENVIADO')

    def test_callback_no_entregado_registra_codigo(self):
        envio = self.evaluar(); enviar_alerta_sms(envio.pk); envio.refresh_from_db()
        self.assertEqual(self.callback(envio, 'undelivered', ErrorCode='30003').status_code, 204)
        envio.refresh_from_db(); self.assertEqual((envio.estado, envio.codigo_error), ('NO_ENTREGADO', '30003'))

    def test_rechaza_callback_sin_firma_o_con_cuenta_sid_telefono_o_estado_incorrectos(self):
        envio = self.evaluar(); enviar_alerta_sms(envio.pk); envio.refresh_from_db()
        url = callback_url(envio.pk).removeprefix(AJUSTES['TWILIO_PUBLIC_BASE_URL'])
        self.assertEqual(self.client.post(url, {'MessageStatus': 'delivered'}).status_code, 403)
        for cambios, esperado in (({'AccountSid': 'AC' + '9' * 32}, 403), ({'MessageSid': 'SM' + '9' * 32}, 409),
                                  ({'To': '+56933334444'}, 409), ({'MessageStatus': 'inventado'}, 400)):
            with self.subTest(cambios=cambios):
                self.assertEqual(self.callback(envio, **cambios).status_code, esperado)
        envio.refresh_from_db(); self.assertEqual(envio.estado, 'ACEPTADO')

    def test_callback_no_puede_confirmar_fila_que_no_fue_intentada(self):
        envio = self.evaluar()
        self.assertEqual(self.callback(envio).status_code, 409)

    def test_firma_de_callback_no_admite_alteracion_del_estado(self):
        envio = self.evaluar(); enviar_alerta_sms(envio.pk); envio.refresh_from_db()
        datos = {'AccountSid': AJUSTES['TWILIO_ACCOUNT_SID'], 'MessageSid': envio.twilio_sid,
                 'MessageStatus': 'queued', 'To': envio.destinatario}
        firma = RequestValidator(AJUSTES['TWILIO_AUTH_TOKEN']).compute_signature(callback_url(envio.pk), datos)
        datos['MessageStatus'] = 'delivered'
        respuesta = self.client.post(callback_url(envio.pk).removeprefix(AJUSTES['TWILIO_PUBLIC_BASE_URL']),
            urlencode(datos), content_type='application/x-www-form-urlencoded', HTTP_X_TWILIO_SIGNATURE=firma)
        self.assertEqual(respuesta.status_code, 403)
        envio.refresh_from_db(); self.assertEqual(envio.estado, 'ACEPTADO')

    def test_api_exige_administrador_activo_y_no_expone_telefono_ni_token(self):
        self.evaluar()
        for ruta in ('estado/', 'historial/'):
            respuesta = self.client.get(RUTA + ruta)
            self.assertEqual(respuesta.status_code, 200)
            self.assertNotIn(AJUSTES['TWILIO_AUTH_TOKEN'], respuesta.content.decode())
            self.assertNotIn('+56911112222', respuesta.content.decode())
        self.admin.activo = False; self.admin.save()
        self.assertEqual(self.client.get(RUTA + 'estado/').status_code, 403)
        lector = Usuario.objects.create_user(email='sms-lector@example.com', nombres='Lector', apellidos='SMS')
        self.client.force_authenticate(lector)
        self.assertEqual(self.client.get(RUTA + 'historial/').status_code, 403)
        self.assertEqual(self.client.post(RUTA + 'procesar-pendientes/', {}, format='json').status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(RUTA + 'estado/').status_code, 401)

    def test_administrador_por_rol_tambien_puede_consultar(self):
        rol = Rol.objects.create(codigo='administrador', nombre='Administrador SMS')
        usuario = Usuario.objects.create_user(email='sms-rol@example.com', rol=rol)
        self.client.force_authenticate(usuario)
        self.assertEqual(self.client.get(RUTA + 'estado/').status_code, 200)

    def test_historial_del_admin_es_solo_lectura_y_muestra_telefono_oculto(self):
        envio = self.evaluar()
        self.client.force_login(self.admin)
        ruta = f'/admin/productos/envioalertasms/{envio.pk}/change/'
        respuesta = self.client.get(ruta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('+56911112222', respuesta.content.decode())
        self.assertContains(respuesta, '+569*****222')
        self.assertEqual(self.client.post(ruta, {'estado': 'ENTREGADO'}).status_code, 403)
        envio.refresh_from_db(); self.assertEqual(envio.estado, 'PENDIENTE')

    def test_historial_pagina_25_y_filtra_antes_de_paginar(self):
        base = self.evaluar()
        for i in range(29):
            EnvioAlertaSMS.objects.create(producto=self.producto, bodega=self.bodega, ciclo=uuid.uuid4(), nivel=1,
                sku=f'SMS-{i}', producto_nombre='Producto', bodega_nombre='Central', cantidad=5, minimo=5,
                destinatario=base.destinatario, mensaje=base.mensaje, estado='PENDIENTE' if i < 27 else 'ENTREGADO')
        respuesta = self.client.get(RUTA + 'historial/', {'estado': 'PENDIENTE'})
        self.assertEqual((respuesta.data['count'], len(respuesta.data['results'])), (28, 25))
        respuesta = self.client.get(RUTA + 'historial/', {'estado': 'PENDIENTE', 'page': 2})
        self.assertEqual(len(respuesta.data['results']), 3)
        self.assertEqual(self.client.get(RUTA + 'historial/', {'estado': 'inventado'}).status_code, 400)

    def test_proceso_api_respeta_cuota_y_comando_no_reintenta_inciertos(self):
        envio = self.evaluar()
        self.assertEqual(self.client.post(RUTA + 'procesar-pendientes/', {}, format='json').status_code, 200)
        EnvioAlertaSMS.objects.filter(pk=envio.pk).update(estado='INCIERTO')
        salida = StringIO()
        call_command('procesar_alertas_sms', stdout=salida)
        self.assertIn('0', salida.getvalue())
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, 1)
        with override_settings(SMS_ALERTAS_ACTIVAS=False):
            self.assertEqual(self.client.post(RUTA + 'procesar-pendientes/', {}, format='json').status_code, 409)
            with self.assertRaises(CommandError):
                call_command('procesar_alertas_sms', stdout=salida)

    def test_proceso_interrumpido_pasa_a_incierto_sin_consumir_otra_cuota(self):
        envio = self.evaluar()
        EnvioAlertaSMS.objects.filter(pk=envio.pk).update(estado='ENVIANDO', intentos=1, ultimo_intento=timezone.now() - timedelta(minutes=6))
        procesar_pendientes_sms()
        envio.refresh_from_db(); self.assertEqual(envio.estado, 'INCIERTO')
        self.proveedor.assert_not_called()

    def test_operaciones_reales_integran_salida_merma_y_minimo_sin_duplicar(self):
        url = '/api/v1/productos/'
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(url + 'registrar-movimiento/', {'producto_id': self.producto.pk,
                'tipo_movimiento': 'SALIDA', 'cantidad': 5}, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(EnvioAlertaSMS.objects.count(), 1)
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(url + 'mermas/', {'producto_id': self.producto.pk,
                'cantidad': 5, 'motivo': 'DAÑO', 'observacion': 'Prueba SMS'}, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(EnvioAlertaSMS.objects.count(), 2)
        self.stock.refresh_from_db(); self.assertEqual(self.stock.cantidad_total, 0)
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, 2)
        self.client.patch(url + f'{self.producto.pk}/stock-minimo/', {'bodega': self.bodega.pk, 'cantidad_minima': 8}, format='json')
        self.assertEqual(EnvioAlertaSMS.objects.count(), 2)

    def test_cambio_de_minimo_puede_disparar_alerta_y_es_idempotente(self):
        url = f'/api/v1/productos/{self.producto.pk}/stock-minimo/'
        for _ in range(2):
            respuesta = self.client.patch(url, {'bodega': self.bodega.pk, 'cantidad_minima': 10}, format='json')
            self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(EnvioAlertaSMS.objects.count(), 1)

    def test_desactivar_producto_cancela_su_cola_sin_cambiar_historia_de_enviados(self):
        envio = self.evaluar()
        respuesta = self.client.delete(f'/api/v1/productos/{self.producto.pk}/')
        self.assertEqual(respuesta.status_code, 200)
        envio.refresh_from_db(); self.assertEqual(envio.estado, 'CANCELADO')
        self.assertEqual(EstadoStockSMS.objects.get().nivel_maximo, 0)

    def test_fallo_de_auditoria_revierte_stock_y_no_crea_cola(self):
        url = '/api/v1/productos/registrar-movimiento/'
        with patch('apps.productos.views_movimientos.registrar_auditoria', side_effect=RuntimeError('simulado')):
            with self.assertLogs('django.request', level='ERROR'), self.assertRaises(RuntimeError):
                self.client.post(url, {'producto_id': self.producto.pk, 'tipo_movimiento': 'SALIDA', 'cantidad': 5}, format='json')
        self.stock.refresh_from_db(); self.assertEqual(self.stock.cantidad_total, 10)
        self.assertFalse(EnvioAlertaSMS.objects.exists())
        self.proveedor.assert_not_called()

    def test_timeout_no_revierte_operacion_confirmada(self):
        self.proveedor.return_value.messages.create.side_effect = TimeoutError('simulado')
        with self.captureOnCommitCallbacks(execute=True), patch('apps.productos.alertas_sms.logger'):
            respuesta = self.client.post('/api/v1/productos/registrar-movimiento/', {
                'producto_id': self.producto.pk, 'tipo_movimiento': 'SALIDA', 'cantidad': 5}, format='json')
        self.assertEqual(respuesta.status_code, 201)
        self.stock.refresh_from_db(); self.assertEqual(self.stock.cantidad_total, 5)
        self.assertTrue(Auditoria.objects.filter(modelo='Movimiento').exists())
        self.assertEqual(EnvioAlertaSMS.objects.get().estado, 'INCIERTO')

    def test_sdk_real_serializa_solicitud_y_deserializa_respuesta_sin_conexion(self):
        envio = self.evaluar()
        respuesta = RespuestaTwilio(201, json.dumps({'sid': 'SM' + '8' * 32, 'status': 'queued', 'error_code': None}))
        with patch(CLIENTE, TwilioReal), patch('twilio.http.http_client.TwilioHttpClient.request', return_value=respuesta) as http:
            enviar_alerta_sms(envio.pk)
        solicitud = http.call_args.kwargs
        self.assertEqual(http.call_args.args[0], 'POST')
        self.assertEqual(solicitud['data']['To'], '+56911112222')
        self.assertEqual(solicitud['data']['From'], '+15005550006')
        self.assertEqual(solicitud['data']['StatusCallback'], callback_url(envio.pk))
        envio.refresh_from_db(); self.assertEqual(envio.estado, 'ACEPTADO')


@override_settings(**AJUSTES)
class CommitSMSTests(TransactionTestCase):
    def test_red_ocurre_tras_commit_y_rollback_descarta_cola_y_callback(self):
        producto = Producto.objects.create(sku='COMMIT-SMS', nombre='Producto')
        bodega = Bodega.objects.create(nombre='Central', direccion='Central')
        StockMinimo.objects.create(producto=producto, bodega=bodega, cantidad_minima=5)
        StockBodega.objects.create(producto=producto, bodega=bodega, cantidad_total=2)
        with patch(CLIENTE) as cliente:
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    evaluar_alerta_sms(producto, bodega)
                    raise RuntimeError('rollback')
            self.assertFalse(EnvioAlertaSMS.objects.exists())
            cliente.assert_not_called()
            cliente.return_value.messages.create.return_value = SimpleNamespace(sid='SM' + '4' * 32, status='queued', error_code=None)
            with transaction.atomic():
                evaluar_alerta_sms(producto, bodega)
                cliente.assert_not_called()
            cliente.return_value.messages.create.assert_called_once()
            self.assertFalse(transaction.get_connection().in_atomic_block)
            self.assertEqual(EnvioAlertaSMS.objects.get().estado, 'ACEPTADO')


@override_settings(**AJUSTES)
class ConcurrenciaSMSTests(TransactionTestCase):
    def preparar(self):
        bodega = Bodega.objects.create(nombre='Central', direccion='Central')
        for i in range(2):
            producto = Producto.objects.create(sku=f'CONC-SMS-{i}', nombre='Producto')
            StockBodega.objects.create(producto=producto, bodega=bodega, cantidad_total=2)
            StockMinimo.objects.create(producto=producto, bodega=bodega, cantidad_minima=5)
            with patch('apps.productos.alertas_sms.enviar_alerta_sms'):
                evaluar_alerta_sms(producto, bodega)
        return list(EnvioAlertaSMS.objects.values_list('pk', flat=True))

    def simultaneos(self, ids):
        from threading import Barrier
        barrera = Barrier(2)
        def ejecutar(envio_id):
            close_old_connections()
            try:
                barrera.wait(timeout=10)
                enviar_alerta_sms(envio_id)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            for resultado in ejecutor.map(ejecutar, ids):
                self.assertIsNone(resultado)

    @skipUnlessDBFeature('has_select_for_update')
    def test_dos_procesos_no_envian_dos_veces_el_mismo_pendiente(self):
        ids = self.preparar()
        with patch(CLIENTE) as cliente:
            cliente.return_value.messages.create.return_value = SimpleNamespace(sid='SM' + '7' * 32, status='queued', error_code=None)
            self.simultaneos([ids[0], ids[0]])
            cliente.return_value.messages.create.assert_called_once()
        self.assertEqual(EnvioAlertaSMS.objects.get(pk=ids[0]).intentos, 1)
        self.assertEqual(LimiteDiarioSMS.objects.get().intentos, 1)

    @skipUnlessDBFeature('has_select_for_update')
    @override_settings(SMS_ALERTAS_LIMITE_DIARIO=1)
    def test_dos_productos_simultaneos_no_exceden_cuota_global(self):
        ids = self.preparar()
        with patch(CLIENTE) as cliente:
            cliente.return_value.messages.create.return_value = SimpleNamespace(sid='SM' + '6' * 32, status='queued', error_code=None)
            self.simultaneos(ids)
            cliente.return_value.messages.create.assert_called_once()
        self.assertEqual(LimiteDiarioSMS.objects.get().intentos, 1)
        self.assertEqual(EnvioAlertaSMS.objects.filter(estado='ACEPTADO').count(), 1)
        self.assertEqual(EnvioAlertaSMS.objects.filter(estado='PENDIENTE', intentos=0).count(), 1)
