"""Comprobación del listado de usuarios y perfiles con autenticación válida."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.usuarios.models import Rol, Usuario


class ListadoUsuariosRolesTests(TestCase):
    def setUp(self):
        self.admin_rol = Rol.objects.create(nombre='Administrador', codigo='administrador')
        self.operador_rol = Rol.objects.create(nombre='Operador', codigo='operador')
        self.encargado_rol = Rol.objects.create(nombre='Encargado de bodega', codigo='encargado_bodega')
        self.admin = Usuario.objects.create_user(
            email='admin-listado@example.com', password='PasswordSeguro123!',
            nombres='Admin', apellidos='Pruebas', rol=self.admin_rol,
        )
        self.encargado = Usuario.objects.create_user(
            email='encargado-listado@example.com', password='PasswordSeguro123!',
            nombres='Encargado', apellidos='Pruebas', rol=self.encargado_rol,
        )
        self.client = APIClient()

    def _lista(self, respuesta):
        datos = respuesta.data
        if isinstance(datos, list):
            return datos
        if isinstance(datos, dict):
            if 'results' in datos:
                return datos['results']
            return datos.get('data', [])
        return []

    def test_administrador_ve_usuarios_y_encargado(self):
        self.client.force_authenticate(user=self.admin)
        respuesta = self.client.get('/api/v1/usuarios/')
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        correos = {u['email'] for u in self._lista(respuesta)}
        self.assertIn(self.admin.email, correos)
        self.assertIn(self.encargado.email, correos)

    def test_administrador_ve_los_tres_roles(self):
        self.client.force_authenticate(user=self.admin)
        respuesta = self.client.get('/api/v1/usuarios/roles/')
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        codigos = {rol['codigo'] for rol in self._lista(respuesta)}
        self.assertEqual(codigos, {'administrador', 'operador', 'encargado_bodega'})

    def test_un_usuario_no_administrador_no_ve_usuarios_ni_roles(self):
        self.client.force_authenticate(user=self.encargado)
        self.assertEqual(self.client.get('/api/v1/usuarios/').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/usuarios/roles/').status_code, 403)
