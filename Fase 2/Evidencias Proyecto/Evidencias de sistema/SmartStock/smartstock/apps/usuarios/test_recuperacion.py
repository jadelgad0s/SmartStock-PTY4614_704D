"""Pruebas del proceso de recuperación sin alterar contraseñas reales."""
import re
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.usuarios.models import Rol, Usuario


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    PASSWORD_RESET_TIMEOUT=3600,
)
class RecuperacionClaveTests(TestCase):
    def setUp(self):
        self.rol = Rol.objects.create(nombre='Operador', codigo='operador')
        self.user = Usuario.objects.create_user(
            email='recuperacion@example.com',
            password='ClaveOriginalSegura123!',
            nombres='Persona', apellidos='Pruebas', rol=self.rol,
        )
        self.url = reverse('recuperar_clave')
        mail.outbox.clear()
        cache.clear()

    def _solicitar(self, email):
        return self.client.post(self.url, {'email': email})

    def _enlace(self):
        mensaje = mail.outbox[-1].body
        match = re.search(
            r'http://testserver(/restablecer-clave/([^/]+)/([^/]+)/)', mensaje
        )
        self.assertIsNotNone(match, mensaje)
        return match.group(1), match.group(2), match.group(3)

    def test_formulario_desde_login_y_page_responsive(self):
        response = self.client.get('/')
        self.assertContains(response, reverse('recuperar_clave'))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Correo electrónico')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_recuperacion_envia_enlace_con_token(self):
        respuesta = self._solicitar(self.user.email)
        self.assertRedirects(respuesta, reverse('recuperacion_enviada'))
        self.assertEqual(len(mail.outbox), 1)
        url, uidb64, token = self._enlace()
        self.assertTrue(default_token_generator.check_token(self.user, token))
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('set-password', resp['Location'])

    def test_correo_corporativo_html_con_fallback_texto(self):
        from django.contrib.staticfiles import finders
        self._solicitar(self.user.email)
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.subject, 'Recupera tu contraseña de SmartStock')
        self.assertIn('http://testserver/restablecer-clave/', correo.body)
        self.assertIn('El enlace vence en 1 hora', correo.body)
        htmls = [
            alternativa.content
            for alternativa in correo.alternatives
            if alternativa.mimetype == 'text/html'
        ]
        self.assertEqual(len(htmls), 1)
        html = htmls[0]
        self.assertIn('Restablecer contraseña', html)
        self.assertIn('http://testserver/restablecer-clave/', html)
        self.assertIn('src="cid:smartstock-logo"', html)
        self.assertIn('Si el botón no funciona', html)
        self.assertIn('1 hora', html)
        self.assertIsNotNone(finders.find('branding/smartstock-mark.png'))

    def test_favicon_legacy_disponible(self):
        respuesta = self.client.get('/favicon.ico')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'image/x-icon')

    def test_token_jwt_anterior_queda_revocado_al_cambiar_clave(self):
        from rest_framework.exceptions import AuthenticationFailed
        from rest_framework_simplejwt.authentication import JWTAuthentication
        from rest_framework_simplejwt.tokens import RefreshToken
        access = str(RefreshToken.for_user(self.user).access_token)
        auth = JWTAuthentication()
        validado = auth.get_validated_token(access)
        self.assertEqual(auth.get_user(validado).pk, self.user.pk)

        self._solicitar(self.user.email)
        enlace, _, _ = self._enlace()
        formulario_url = self.client.get(enlace)['Location']
        respuesta = self.client.post(formulario_url, {
            'new_password1': 'NuevaClaveSegura987!',
            'new_password2': 'NuevaClaveSegura987!',
        })
        self.assertRedirects(respuesta, reverse('clave_actualizada'))
        self.user.refresh_from_db()
        with self.assertRaises(AuthenticationFailed):
            auth.get_user(validado)

    def test_correo_desconocido_misma_confirmacion_sin_email(self):
        respuesta = self._solicitar('nadie@example.com')
        self.assertRedirects(respuesta, reverse('recuperacion_enviada'))
        self.assertEqual(len(mail.outbox), 0)

    def test_cuenta_inactiva_no_recibe_correo(self):
        self.user.activo = False
        self.user.save(update_fields=['activo'])
        respuesta = self._solicitar(self.user.email)
        self.assertRedirects(respuesta, reverse('recuperacion_enviada'))
        self.assertEqual(len(mail.outbox), 0)

    def test_cambiar_clave_invalida_el_enlace_previo(self):
        self._solicitar(self.user.email)
        url, uidb64, token = self._enlace()
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 302)
        nueva_url = respuesta['Location']
        formulario = self.client.post(nueva_url, {
            'new_password1': 'NuevaClaveSegura987!',
            'new_password2': 'NuevaClaveSegura987!',
        })
        self.assertRedirects(formulario, reverse('clave_actualizada'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NuevaClaveSegura987!'))
        self.assertFalse(self.user.check_password('ClaveOriginalSegura123!'))
        self.assertFalse(default_token_generator.check_token(self.user, token))
        self.assertContains(self.client.get(url), 'Enlace inválido o vencido')

    def test_token_caduca(self):
        self._solicitar(self.user.email)
        url, uidb64, token = self._enlace()
        fecha_futura = timezone.now().replace(tzinfo=None) + timedelta(hours=2)
        with patch.object(default_token_generator, '_now', return_value=fecha_futura):
            self.assertFalse(default_token_generator.check_token(self.user, token))
            self.assertContains(self.client.get(url), 'Enlace inválido o vencido')

    def test_formulario_rechaza_passwords_diferentes(self):
        self._solicitar(self.user.email)
        url, _, _ = self._enlace()
        nueva_url = self.client.get(url)['Location']
        respuesta = self.client.post(nueva_url, {
            'new_password1': 'UnaClaveSegura123!',
            'new_password2': 'OtraClaveSegura123!',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'no coinciden')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('ClaveOriginalSegura123!'))
