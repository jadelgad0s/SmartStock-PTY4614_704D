"""Autorización del historial de auditoría."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.usuarios.models import Rol, Usuario


class AuditoriaApiTests(TestCase):
    def setUp(self):
        rol_admin = Rol.objects.create(nombre='Administrador', codigo='administrador')
        rol_operador = Rol.objects.create(nombre='Operador', codigo='operador')
        self.admin = Usuario.objects.create_user(
            email='auditor-admin@example.com', password='Password123!',
            nombres='Administrador', apellidos='Prueba', rol=rol_admin,
        )
        self.operador = Usuario.objects.create_user(
            email='auditor-operador@example.com', password='Password123!',
            nombres='Operador', apellidos='Prueba', rol=rol_operador,
        )
        Auditoria.objects.create(
            usuario=self.admin, accion='CREATE', modelo='Producto',
            objeto_id='1', descripcion='Producto creado desde prueba',
        )
        self.client = APIClient()

    def test_administrador_puede_consultar_auditoria(self):
        self.client.force_authenticate(user=self.admin)
        respuesta = self.client.get('/api/v1/auditoria/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.data['data']), 1)
        self.assertEqual(respuesta.data['data'][0]['descripcion'], 'Producto creado desde prueba')

    def test_operador_no_puede_consultar_auditoria(self):
        self.client.force_authenticate(user=self.operador)
        respuesta = self.client.get('/api/v1/auditoria/')
        self.assertEqual(respuesta.status_code, 403)

    def test_sin_autenticacion_rechaza_consulta(self):
        self.client.force_authenticate(user=None)
        respuesta = self.client.get('/api/v1/auditoria/')
        self.assertEqual(respuesta.status_code, 401)
