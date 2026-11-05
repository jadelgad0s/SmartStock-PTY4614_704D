"""Envío transaccional mediante API HTTPS para servicios sin salida SMTP."""
import base64
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    """Backend Django EmailMessage usando HTTPS en vez de puertos SMTP."""

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        api_key = getattr(settings, 'RESEND_API_KEY', '')
        if not api_key:
            raise ImproperlyConfigured(
                'Falta RESEND_API_KEY. Configura el proveedor de correo en Render.'
            )

        enviados = 0
        for mensaje in email_messages:
            destinatarios = mensaje.recipients()
            if not destinatarios:
                continue

            cuerpo = {
                'from': mensaje.from_email or settings.DEFAULT_FROM_EMAIL,
                'to': destinatarios,
                'subject': mensaje.subject,
                'text': mensaje.body,
            }
            for alternativa in getattr(mensaje, 'alternatives', []):
                if alternativa.mimetype == 'text/html':
                    cuerpo['html'] = alternativa.content
                    break

            # Insertar el logo dentro del mensaje (CID). No depende de
            # imágenes remotas que muchos clientes de correo bloquean.
            if 'cid:smartstock-logo' in cuerpo.get('html', ''):
                logo = (settings.BASE_DIR / 'static' / 'branding' /
                        'smartstock-mark.png')
                cuerpo['attachments'] = [{
                    'filename': 'smartstock-logo.png',
                    'content_type': 'image/png',
                    'content_id': 'smartstock-logo',
                    'content': base64.b64encode(logo.read_bytes()).decode('ascii'),
                }]

            solicitud = Request(
                'https://api.resend.com/emails',
                data=json.dumps(cuerpo).encode('utf-8'),
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    # Evita identificar la solicitud como Python-urllib por defecto.
                    'User-Agent': 'SmartStock/1.0',
                },
                method='POST',
            )
            try:
                with urlopen(solicitud, timeout=12) as respuesta:
                    if not 200 <= respuesta.status < 300:
                        raise OSError(f'Error enviando correo: HTTP {respuesta.status}')
                enviados += 1
            except HTTPError as error:
                # Leer solamente la respuesta de error del proveedor; jamás el
                # cuerpo del correo, la clave API ni la URL de restablecimiento.
                nombre = 'respuesta_no_json'
                detalle = 'Sin detalle JSON del proveedor'
                try:
                    respuesta_error = json.loads(error.read(4096).decode('utf-8'))
                    if isinstance(respuesta_error, dict):
                        nombre = str(respuesta_error.get('name') or 'sin_nombre')[:80]
                        detalle = str(respuesta_error.get('message') or 'Sin mensaje')[:300]
                except (ValueError, UnicodeError):
                    pass

                # Evitar que un proveedor reproduzca accidentalmente la clave.
                nombre = nombre.replace(api_key, '[REDACTED]')
                detalle = detalle.replace(api_key, '[REDACTED]')
                # Cuando Resend no entrega JSON, registrar metadatos de la
                # respuesta (sin HTML, destinatarios ni secretos).
                tipo_contenido = error.headers.get('Content-Type', '').split(';')[0].strip().lower()
                if tipo_contenido not in ('application/json', 'text/html', 'text/plain'):
                    tipo_contenido = 'otro'
                nombre_servidor = error.headers.get('Server', '').lower()
                servidor = 'cloudflare' if 'cloudflare' in nombre_servidor else 'otro'
                cf_ray = error.headers.get('CF-Ray', '')
                cf_ray = ''.join(char for char in cf_ray if char.isalnum() or char in '-._')[:90]
                logger.error(
                    'Resend rechazó el envío: HTTP %s, tipo=%s, detalle=%s, '
                    'content_type=%s, servidor=%s, cf_ray=%s',
                    error.code, nombre, detalle,
                    tipo_contenido, servidor, cf_ray or 'no',
                )
                if not self.fail_silently:
                    raise
            except (URLError, OSError):
                logger.exception('Error de conexión al servicio de correo de SmartStock')
                if not self.fail_silently:
                    raise
        return enviados
