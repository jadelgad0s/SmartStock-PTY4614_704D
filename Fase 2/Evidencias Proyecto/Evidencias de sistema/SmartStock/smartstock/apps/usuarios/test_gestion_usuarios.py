"""Listado paginado, formularios y protecciones para gestión de usuarios."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.usuarios.models import Rol, Usuario


class GestionUsuariosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(nombre='Administrador', codigo='administrador', descripcion='Administración del sistema.')
        cls.rol_op = Rol.objects.create(nombre='Operador', codigo='operador', descripcion='Registra entradas y salidas.')
        cls.rol_inactivo = Rol.objects.create(nombre='Rol histórico', codigo='historico', activo=False)
        cls.admin = Usuario.objects.create_user(email='gestion-admin@example.com', nombres='Admin', apellidos='Prueba', rol=cls.rol_admin)
        cls.operador = Usuario.objects.create_user(email='gestion-op@example.com', nombres='Operador', apellidos='Prueba', rol=cls.rol_op)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def crear_varios(self, cantidad, **extra):
        return Usuario.objects.bulk_create([
            Usuario(email=f'persona{i:03}@example.com', nombres=f'Persona {i:03}', apellidos='Prueba', rol=self.rol_op, **extra)
            for i in range(cantidad)
        ])

    def datos_nuevo(self, **extra):
        return {'email': 'nuevo@example.com', 'nombres': 'Nueva', 'apellidos': 'Persona', 'telefono': '+56 9 1234 5678',
                'rol_id': self.rol_op.pk, 'password': 'UnicaClaveFuerte-83!', 'password_confirmacion': 'UnicaClaveFuerte-83!'} | extra

    def test_paginacion_25_usuarios_y_filtros_antes_de_paginar(self):
        personas = self.crear_varios(55)
        ids = []
        for pagina in (1, 2, 3):
            r = self.client.get('/api/v1/usuarios/', {'search': 'Persona', 'rol': self.rol_op.pk, 'activo': 'true', 'page': pagina})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data['count'], 55)
            self.assertEqual(len(r.data['results']), 25 if pagina < 3 else 5)
            ids.extend(u['id'] for u in r.data['results'])
        self.assertEqual(ids, [p.pk for p in personas])
        self.assertEqual(len(set(ids)), 55)

    def test_nombre_completo_correo_inactivos_y_orden_descendente(self):
        personas = self.crear_varios(3, activo=False)
        for search in ('Persona 001 Prueba', 'persona001@example.com'):
            r = self.client.get('/api/v1/usuarios/', {'search': search, 'activo': 'false'})
            self.assertEqual([u['id'] for u in r.data['results']], [personas[1].pk])
        r = self.client.get('/api/v1/usuarios/', {'search': 'Persona', 'activo': 'false', 'ordering': '-nombres,-apellidos,-id'})
        self.assertEqual([u['id'] for u in r.data['results']], [p.pk for p in personas][::-1])

    def test_orden_alfabetico_desempata_por_id(self):
        personas = self.crear_varios(27)
        Usuario.objects.filter(pk__in=[p.pk for p in personas]).update(nombres='Igual', apellidos='Igual')
        r1 = self.client.get('/api/v1/usuarios/', {'search': 'Igual'})
        r2 = self.client.get('/api/v1/usuarios/', {'search': 'Igual', 'page': 2})
        self.assertEqual([u['id'] for u in r1.data['results'] + r2.data['results']], [p.pk for p in personas])

    def test_paginas_invalidas_ultima_y_filtro_vacio(self):
        self.crear_varios(26)
        for page in ('0', '-1', 'abc', '999999'):
            self.assertEqual(self.client.get('/api/v1/usuarios/', {'page': page}).status_code, 404)
        r = self.client.get('/api/v1/usuarios/', {'page': 'last'})
        self.assertEqual(len(r.data['results']), 3)
        self.assertEqual(self.client.get('/api/v1/usuarios/', {'rol': 'abc'}).status_code, 400)
        r = self.client.get('/api/v1/usuarios/', {'search': 'inexistente'})
        self.assertEqual(r.data['count'], 0)
        self.assertEqual(r.data['results'], [])

    def test_opciones_muestra_roles_historicos_y_requisitos_configurados(self):
        r = self.client.get('/api/v1/usuarios/opciones/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual({p['id'] for p in r.data['data']['roles']}, {self.rol_admin.pk, self.rol_op.pk, self.rol_inactivo.pk})
        historico = next(p for p in r.data['data']['roles'] if p['id'] == self.rol_inactivo.pk)
        self.assertFalse(historico['activo'])
        self.assertTrue(any('8' in texto for texto in r.data['data']['password_requisitos']))
        self.assertEqual(len(r.data['data']['password_requisitos']), 4)

    def test_detalle_identifica_cuentas_protegidas_sin_filtrar_password(self):
        superusuario = Usuario.objects.create_superuser(email='super@example.com', nombres='Super', apellidos='Sin rol')
        self.rol_admin.nombre = 'Jefatura'
        self.rol_admin.save(update_fields=['nombre'])
        for persona, protegido in ((self.admin, True), (superusuario, True), (self.operador, False)):
            r = self.client.get(f'/api/v1/usuarios/{persona.pk}/')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data['cuenta_protegida'], protegido)
            self.assertNotIn('password', r.data)
        listado = self.client.get('/api/v1/usuarios/').data['results']
        self.assertEqual(next(p for p in listado if p['id'] == self.admin.pk)['cuenta_protegida'], True)

    def test_crear_usuario_con_confirmacion_real_registra_hash_y_auditoria(self):
        r = self.client.post('/api/v1/usuarios/', self.datos_nuevo(), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        persona = Usuario.objects.get(pk=r.data['data']['id'])
        self.assertTrue(persona.check_password('UnicaClaveFuerte-83!'))
        self.assertEqual(persona.telefono, '+56 9 1234 5678')
        self.assertNotIn('password', r.data['data'])
        self.assertTrue(Auditoria.objects.filter(modelo='Usuario', objeto_id=str(persona.pk), accion='CREATE').exists())

    def test_confirmacion_incorrecta_contrasena_debil_y_rol_inactivo_no_crean(self):
        casos = [({'password_confirmacion': 'Diferente'}, 'password_confirmacion'),
                 ({'password': '12345678', 'password_confirmacion': '12345678'}, 'password'),
                 ({'rol_id': self.rol_inactivo.pk}, 'rol_id')]
        for cambio, campo in casos:
            r = self.client.post('/api/v1/usuarios/', self.datos_nuevo(**cambio), format='json')
            self.assertEqual(r.status_code, 400, r.data)
            self.assertIn(campo, r.data['errores'])
        self.assertFalse(Usuario.objects.filter(email='nuevo@example.com').exists())

    def test_contrasena_no_recorta_espacios_y_valida_similitud_con_correo(self):
        clave = '  Frase-segura-82!  '
        r = self.client.post('/api/v1/usuarios/', self.datos_nuevo(password=clave, password_confirmacion=clave), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        persona = Usuario.objects.get(pk=r.data['data']['id'])
        self.assertTrue(persona.check_password(clave))
        self.assertFalse(persona.check_password(clave.strip()))
        r = self.client.post('/api/v1/usuarios/', self.datos_nuevo(email='personalidad@example.com', password='personalidad', password_confirmacion='personalidad'), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('password', r.data['errores'])

    def test_correo_duplicado_rechaza_tambien_datos_historicos_en_mayusculas(self):
        Usuario.objects.create_user(email='DUPLICADO@EXAMPLE.COM', nombres='Otra', apellidos='Persona', rol=self.rol_op)
        r = self.client.post('/api/v1/usuarios/', self.datos_nuevo(email='duplicado@example.com'), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('email', r.data['errores'])

    def test_error_de_auditoria_revierte_la_creacion(self):
        with patch('apps.usuarios.views.registrar_auditoria', side_effect=RuntimeError('Fallo de auditoría')):
            with self.assertRaises(RuntimeError):
                self.client.post('/api/v1/usuarios/', self.datos_nuevo(), format='json')
        self.assertFalse(Usuario.objects.filter(email='nuevo@example.com').exists())

    def test_editar_admin_sin_enviar_rol_y_preservar_usuario_con_rol_inactivo(self):
        r = self.client.patch(f'/api/v1/usuarios/{self.admin.pk}/', {'nombres': 'Administrador actualizado', 'telefono': '+56 9 9999 0000'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['data']['cuenta_protegida'])
        self.operador.rol = self.rol_inactivo
        self.operador.save(update_fields=['rol'])
        r = self.client.patch(f'/api/v1/usuarios/{self.operador.pk}/', {'telefono': '+56 9 0000 9999'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['data']['rol']['id'], self.rol_inactivo.pk)

    def test_solo_admin_activo_accede_a_listado_detalle_y_opciones(self):
        inactivo = Usuario.objects.create_user(email='admin-inactivo@example.com', nombres='Admin', apellidos='Inactivo', rol=self.rol_admin, activo=False)
        for actor, estado in ((None, 401), (self.operador, 403), (inactivo, 403)):
            self.client.force_authenticate(user=actor)
            for ruta in ('/api/v1/usuarios/', '/api/v1/usuarios/opciones/', f'/api/v1/usuarios/{self.admin.pk}/'):
                self.assertEqual(self.client.get(ruta).status_code, estado)

    def test_detalle_incluye_telefono_fechas_y_ultimo_acceso(self):
        fecha = datetime(2026, 10, 28, 2, 30, tzinfo=timezone.utc)
        Usuario.objects.filter(pk=self.operador.pk).update(ultimo_login=fecha, telefono='+56 9 1234 5678')
        datos = self.client.get(f'/api/v1/usuarios/{self.operador.pk}/').data
        self.assertEqual(datos['telefono'], '+56 9 1234 5678')
        self.assertIsNotNone(datos['ultimo_login'])
        self.assertIn('fecha_creacion', datos)
        self.assertIn('fecha_modificacion', datos)

    def test_listado_no_hace_una_consulta_por_rol(self):
        self.crear_varios(30)
        with self.assertNumQueries(2):
            r = self.client.get('/api/v1/usuarios/')
        self.assertEqual(len(r.data['results']), 25)
