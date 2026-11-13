"""Pruebas para errores de Resend sin revelar credenciales ni mensajes."""
import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from apps.usuarios.email_backends import ResendEmailBackend


@override_settings(
    RESEND_API_KEY='re_SUPER_SECRETA',
    DEFAULT_FROM_EMAIL='SmartStock <contacto@smartstockchile.cl>',
)
class ResendDiagnosticoTests(SimpleTestCase):
    def setUp(self):
        self.mensaje = EmailMessage(
            subject='Prueba',
            body='Enlace privado que no debe aparecer en los registros',
            to=['destinatario@example.com'],
        )

    def test_error_403_json_muestra_motivo_sin_filtrar_clave(self):
        cuerpo = json.dumps({
            'name': 'validation_error',
            'message': 'API key re_SUPER_SECRETA rechazada',
        }).encode()
        error = HTTPError(
            'https://api.resend.com/emails', 403, 'Forbidden',
            {'Content-Type': 'application/json'}, io.BytesIO(cuerpo)
        )
        with patch('apps.usuarios.email_backends.urlopen', side_effect=error):
            with self.assertLogs('apps.usuarios.email_backends', level='ERROR') as logs:
                with self.assertRaises(HTTPError):
                    ResendEmailBackend().send_messages([self.mensaje])
        registrado = '\n'.join(logs.output)
        self.assertIn('HTTP 403', registrado)
        self.assertIn('validation_error', registrado)
        self.assertIn('[REDACTED]', registrado)
        self.assertNotIn('re_SUPER_SECRETA', registrado)
        self.assertNotIn(self.mensaje.body, registrado)

    def test_error_403_html_no_imprime_pagina_del_proxy(self):
        error = HTTPError(
            'https://api.resend.com/emails', 403, 'Forbidden',
            {'Content-Type': 'text/html; charset=utf-8',
             'Server': 'cloudflare',
             'CF-Ray': '12345abc-SCL'},
            io.BytesIO(b'<html><body>Cloudflare bloqueado</body></html>'),
        )
        with patch('apps.usuarios.email_backends.urlopen', side_effect=error):
            with self.assertLogs('apps.usuarios.email_backends', level='ERROR') as logs:
                with self.assertRaises(HTTPError):
                    ResendEmailBackend().send_messages([self.mensaje])
        registrado = '\n'.join(logs.output)
        self.assertIn('respuesta_no_json', registrado)
        self.assertIn('content_type=text/html', registrado)
        self.assertIn('servidor=cloudflare', registrado)
        self.assertIn('cf_ray=12345abc-SCL', registrado)
        self.assertNotIn('Cloudflare bloqueado', registrado)

    def test_respuesta_exitosa_contabiliza_envio(self):
        class Respuesta:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        with patch('apps.usuarios.email_backends.urlopen', return_value=Respuesta()):
            resultado = ResendEmailBackend().send_messages([self.mensaje])
        self.assertEqual(resultado, 1)

    def test_correo_html_adjunta_logo_cid_en_resend(self):
        import base64
        import json
        from pathlib import Path
        from django.conf import settings
        from django.core.mail import EmailMultiAlternatives

        mensaje = EmailMultiAlternatives(
            subject='Recupera tu contraseña',
            body='Versión de texto con enlace',
            to=['destinatario@example.com'],
        )
        mensaje.attach_alternative(
            '<h1>SmartStock</h1><img src="cid:smartstock-logo" alt="SmartStock">',
            'text/html',
        )

        class Respuesta:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        with patch('apps.usuarios.email_backends.urlopen', return_value=Respuesta()) as llamada:
            enviados = ResendEmailBackend().send_messages([mensaje])

        self.assertEqual(enviados, 1)
        payload = json.loads(llamada.call_args.args[0].data)
        self.assertEqual(payload['text'], mensaje.body)
        self.assertIn('cid:smartstock-logo', payload['html'])
        self.assertEqual(len(payload['attachments']), 1)
        adjunto = payload['attachments'][0]
        self.assertEqual(adjunto['content_id'], 'smartstock-logo')
        self.assertEqual(adjunto['content_type'], 'image/png')
        self.assertEqual(adjunto['filename'], 'smartstock-logo.png')
        esperado = (settings.BASE_DIR / 'static' / 'branding' /
                    'smartstock-mark.png').read_bytes()
        self.assertEqual(base64.b64decode(adjunto['content']), esperado)
        self.assertTrue(esperado.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_correo_plano_no_agrega_adjunto(self):
        import json
        class Respuesta:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        with patch('apps.usuarios.email_backends.urlopen', return_value=Respuesta()) as llamada:
            enviados = ResendEmailBackend().send_messages([self.mensaje])
        self.assertEqual(enviados, 1)
        payload = json.loads(llamada.call_args.args[0].data)
        self.assertNotIn('attachments', payload)

    def test_envio_identifica_aplicacion_y_acepta_json(self):
        class Respuesta:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        with patch('apps.usuarios.email_backends.urlopen', return_value=Respuesta()) as llamada:
            enviados = ResendEmailBackend().send_messages([self.mensaje])
        self.assertEqual(enviados, 1)
        solicitud = llamada.call_args.args[0]
        self.assertEqual(solicitud.get_header('User-agent'), 'SmartStock/1.0')
        self.assertEqual(solicitud.get_header('Accept'), 'application/json')
        self.assertEqual(solicitud.get_header('Content-type'), 'application/json')
