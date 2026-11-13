"""Recuperación de claves con el modelo Usuario personalizado de SmartStock."""
import hashlib
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.views import (
    PasswordResetView, PasswordResetDoneView,
    PasswordResetConfirmView, PasswordResetCompleteView,
)
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy

from .models import Usuario


class RecuperacionClaveForm(PasswordResetForm):
    """Usuario usa activo en lugar de is_active; evita enumerar direcciones."""

    def get_users(self, email):
        usuarios = Usuario.objects.filter(email__iexact=email, activo=True)
        return (usuario for usuario in usuarios if usuario.has_usable_password())


class SolicitarRecuperacionView(PasswordResetView):
    template_name = 'usuarios/recuperar_clave.html'
    email_template_name = 'usuarios/correo_recuperacion.txt'
    html_email_template_name = 'usuarios/correo_recuperacion.html'
    subject_template_name = 'usuarios/asunto_recuperacion.txt'
    form_class = RecuperacionClaveForm
    success_url = reverse_lazy('recuperacion_enviada')

    def form_valid(self, form):
        # Mitigar envíos repetidos sin revelar si la cuenta existe.
        correo = form.cleaned_data['email'].strip().lower()
        hash_correo = hashlib.sha256(correo.encode('utf-8')).hexdigest()
        llave = 'recuperar_clave:' + hash_correo
        if not cache.add(llave, True, timeout=120):
            return HttpResponseRedirect(self.get_success_url())
        return super().form_valid(form)


class RecuperacionEnviadaView(PasswordResetDoneView):
    template_name = 'usuarios/recuperacion_enviada.html'


class EstablecerNuevaClaveView(PasswordResetConfirmView):
    template_name = 'usuarios/nueva_clave.html'
    success_url = reverse_lazy('clave_actualizada')


class ClaveActualizadaView(PasswordResetCompleteView):
    template_name = 'usuarios/clave_actualizada.html'
