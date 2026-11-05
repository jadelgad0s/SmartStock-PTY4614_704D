"""Historial completo, filtros, permisos y reportes de auditoría."""
import csv
import io
from datetime import datetime, timezone as tz

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.usuarios.models import Rol, Usuario


@override_settings(TIME_ZONE='America/Santiago')
class AuditoriaHistorialTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        rol_admin = Rol.objects.create(nombre='Administrador', codigo='administrador')
        rol_op = Rol.objects.create(nombre='Operador', codigo='operador')
        cls.admin = Usuario.objects.create_user(email='admin-audit@example.com', nombres='Javier', apellidos='Delgado', rol=rol_admin)
        cls.operador = Usuario.objects.create_user(email='op-audit@example.com', nombres='Persona', apellidos='Operadora', rol=rol_op)
        cls.inactivo = Usuario.objects.create_user(email='inactivo-audit@example.com', nombres='Admin', apellidos='Inactivo', rol=rol_admin, activo=False)
        cls.superusuario = Usuario.objects.create_superuser(email='super-audit@example.com', nombres='Super', apellidos='Usuario')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def evento(self, **campos):
        return Auditoria.objects.create(**({'usuario': self.admin, 'accion': 'LOGIN', 'modelo': 'Usuario',
                                           'descripcion': 'Inicio de sesión: admin-audit@example.com'} | campos))

    def varios(self, cantidad, **campos):
        datos = {'usuario': self.admin, 'accion': 'CREATE', 'modelo': 'Movimiento', 'descripcion': 'ENTRADA de 2 unid. SKU: BEBIDA-01'} | campos
        return Auditoria.objects.bulk_create([Auditoria(**datos) for _ in range(cantidad)])

    def csv(self, params=None):
        respuesta = self.client.get('/api/v1/auditoria/exportar/', params or {})
        self.assertEqual(respuesta.status_code, 200)
        contenido_binario = b''.join(respuesta.streaming_content)
        self.assertTrue(contenido_binario.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(respuesta['Cache-Control'], 'no-store')
        contenido = contenido_binario.decode('utf-8-sig')
        filas = list(csv.reader(io.StringIO(contenido), delimiter=';'))
        indice = next(i for i, fila in enumerate(filas) if fila and fila[0] == 'ID')
        return filas[:indice], filas[indice], filas[indice + 1:]

    def test_historial_completo_supera_200_con_25_por_pagina_y_desempate_por_id(self):
        eventos = self.varios(206)
        Auditoria.objects.update(fecha_creacion=datetime(2026, 10, 27, 15, 30, tzinfo=tz.utc))
        ids = []
        for pagina in range(1, 10):
            r = self.client.get('/api/v1/auditoria/historial/', {'page': pagina})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data['count'], 206)
            self.assertEqual(len(r.data['results']), 25 if pagina < 9 else 6)
            ids.extend(e['id'] for e in r.data['results'])
        self.assertEqual(ids, sorted((e.pk for e in eventos), reverse=True))
        self.assertEqual(len(set(ids)), 206)
        self.assertEqual(r.data['zona_horaria'], 'America/Santiago')
        self.assertEqual(r['Cache-Control'], 'no-store')

    def test_filtros_combinados_se_aplican_antes_de_paginar(self):
        eventos = self.varios(28)
        self.varios(3, usuario=self.operador)
        self.varios(3, accion='UPDATE')
        self.varios(3, modelo='Producto')
        self.varios(3, descripcion='Otro SKU')
        r = self.client.get('/api/v1/auditoria/historial/', {
            'search': 'BEBIDA-01', 'usuario': self.admin.pk, 'accion': 'CREATE', 'modelo': 'movimiento', 'page': 2,
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['count'], 28)
        self.assertEqual([e['id'] for e in r.data['results']], [e.pk for e in eventos[:3]][::-1])

    def test_busqueda_por_nombre_completo_correo_y_descripcion(self):
        evento = self.evento(descripcion='Salida SKU: FER-022')
        self.evento(usuario=self.operador, descripcion='Otro evento')
        for texto in ('Javier Delgado', 'admin-audit@example.com', 'FER-022'):
            with self.subTest(texto=texto):
                r = self.client.get('/api/v1/auditoria/historial/', {'search': texto})
                self.assertEqual([e['id'] for e in r.data['results']], [evento.pk])

    def test_fechas_incluyen_dia_local_completo_con_segundos(self):
        fechas = [datetime(2026, 10, 27, 2, 59, 59, tzinfo=tz.utc),
                  datetime(2026, 10, 27, 3, 0, 0, tzinfo=tz.utc),
                  datetime(2026, 10, 28, 2, 59, 59, tzinfo=tz.utc),
                  datetime(2026, 10, 28, 3, 0, 0, tzinfo=tz.utc)]
        eventos = [self.evento() for _ in fechas]
        for e, fecha in zip(eventos, fechas):
            Auditoria.objects.filter(pk=e.pk).update(fecha_creacion=fecha)
        r = self.client.get('/api/v1/auditoria/historial/', {'desde': '2026-10-27', 'hasta': '2026-10-27'})
        self.assertEqual([e['id'] for e in r.data['results']], [eventos[2].pk, eventos[1].pk])
        self.assertEqual(r.data['results'][0]['fecha'], '27/10/2026 23:59:59')
        self.assertTrue(r.data['results'][0]['fecha_iso'].endswith('-03:00'))

    def test_filtros_invalidos_se_rechazan_tambien_en_reportes(self):
        filtros = [{'desde': '2026-02-30'}, {'hasta': 'no-es-fecha'},
                   {'desde': '2026-10-28', 'hasta': '2026-10-27'}, {'hasta': '9999-12-31'},
                   {'usuario': '-1'}, {'usuario': 'abc'}, {'usuario': '99999999999999999999'},
                   {'search': 'x' * 201}, {'modelo': 'x' * 101}, {'accion': 'x' * 21}]
        for ruta in ('historial/', 'exportar/', 'reporte/'):
            for params in filtros:
                with self.subTest(ruta=ruta, params=params):
                    self.assertEqual(self.client.get('/api/v1/auditoria/' + ruta, params).status_code, 400)

    def test_paginas_invalidas_y_ultima_pagina(self):
        self.varios(26)
        for pagina in ('0', '-1', 'abc', '999'):
            self.assertEqual(self.client.get('/api/v1/auditoria/historial/', {'page': pagina}).status_code, 404)
        r = self.client.get('/api/v1/auditoria/historial/', {'page': 'last'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data['results']), 1)

    def test_detalle_completo_metadatos_y_usuario_no_identificado(self):
        texto = 'Observación completa.\n' * 200
        e = self.evento(usuario=None, accion='LOGIN_FAILED', descripcion=texto,
                        objeto_id='USUARIO-10', ip_address='192.0.2.10', user_agent='Navegador de prueba')
        r = self.client.get(f'/api/v1/auditoria/{e.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['data']['descripcion'], texto)
        self.assertEqual(r.data['data']['usuario'], 'Usuario no identificado')
        self.assertEqual(r.data['data']['usuario_email'], '')
        self.assertEqual(r.data['data']['accion_etiqueta'], 'Acceso fallido')
        self.assertEqual(r.data['data']['ip_address'], '192.0.2.10')
        self.assertEqual(r.data['data']['user_agent'], 'Navegador de prueba')
        self.assertEqual(r.data['data']['objeto_id'], 'USUARIO-10')
        self.assertEqual(self.client.get('/api/v1/auditoria/999999/').status_code, 404)
        e2 = self.evento(usuario=None)
        r2 = self.client.get(f'/api/v1/auditoria/{e2.pk}/').data['data']
        self.assertIsNone(r2['ip_address'])
        self.assertEqual(r2['user_agent'], '')

    def test_opciones_incluyen_usuarios_historicos_y_eventos_sin_usuario(self):
        self.evento()
        self.evento(usuario=self.inactivo, accion='CUSTOM', modelo='Módulo histórico')
        sin_usuario = self.evento(usuario=None, accion='LOGIN_FAILED')
        datos = self.client.get('/api/v1/auditoria/opciones/').data['data']
        self.assertEqual({u['id'] for u in datos['usuarios']}, {self.admin.pk, self.inactivo.pk})
        self.assertTrue(datos['sin_usuario'])
        self.assertIn('Módulo histórico', datos['modelos'])
        self.assertIn({'valor': 'CUSTOM', 'etiqueta': 'CUSTOM'}, datos['acciones'])
        r = self.client.get('/api/v1/auditoria/historial/', {'usuario': 'sin_usuario'})
        self.assertEqual([e['id'] for e in r.data['results']], [sin_usuario.pk])
        self.assertEqual(self.client.get('/api/v1/auditoria/historial/', {'usuario': self.inactivo.pk}).data['count'], 1)

    def test_api_legacy_conserva_formato_y_limite_200(self):
        self.varios(205)
        r = self.client.get('/api/v1/auditoria/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['success'])
        self.assertEqual(len(r.data['data']), 200)
        self.assertEqual(set(r.data['data'][0]), {'fecha', 'usuario', 'accion', 'modelo', 'descripcion'})

    def test_solo_admin_activo_o_superusuario_pueden_consultar_y_exportar(self):
        e = self.evento()
        rutas = ['', 'historial/', 'opciones/', 'exportar/', 'reporte/', f'{e.pk}/']
        for usuario, estado in ((None, 401), (self.operador, 403), (self.inactivo, 403), (self.superusuario, 200)):
            self.client.force_authenticate(user=usuario)
            for ruta in rutas:
                with self.subTest(usuario=usuario, ruta=ruta):
                    respuesta = self.client.get('/api/v1/auditoria/' + ruta)
                    self.assertEqual(respuesta.status_code, estado)
                    if getattr(respuesta, 'streaming', False):
                        list(respuesta.streaming_content)

    def test_endpoints_son_solo_lectura(self):
        e = self.evento()
        for ruta in ('', 'historial/', 'opciones/', 'exportar/', 'reporte/', f'{e.pk}/'):
            for metodo in ('post', 'put', 'patch', 'delete'):
                with self.subTest(ruta=ruta, metodo=metodo):
                    r = getattr(self.client, metodo)('/api/v1/auditoria/' + ruta, {}, format='json')
                    self.assertEqual(r.status_code, 405)
        self.assertEqual(Auditoria.objects.count(), 1)

    def test_csv_exporta_todas_las_paginas_filtradas_con_bom_y_metadatos(self):
        texto = 'Ajuste; SKU: FER-022 "especial"\nSegunda línea'
        eventos = self.varios(52, descripcion=texto)
        self.evento(modelo='Usuario')
        metadatos, cabecera, filas = self.csv({'modelo': 'Movimiento', 'search': 'FER-022', 'page': '2'})
        self.assertEqual(len(filas), 52)
        self.assertEqual([int(f[0]) for f in filas], [e.pk for e in eventos][::-1])
        self.assertEqual(filas[0][cabecera.index('Descripción')], texto)
        self.assertIn(['Total de eventos', '52'], metadatos)
        self.assertIn(['Módulo', 'Movimiento'], metadatos)
        self.assertIn(['Búsqueda', 'FER-022'], metadatos)
        self.assertIn(['Zona horaria', 'America/Santiago'], metadatos)

    def test_csv_no_incluye_eventos_creados_despues_de_iniciar_reporte(self):
        original = self.evento()
        r = self.client.get('/api/v1/auditoria/exportar/')
        self.evento(descripcion='Nuevo evento posterior')
        texto = b''.join(r.streaming_content).decode('utf-8-sig')
        self.assertIn('Total de eventos;1', texto)
        self.assertIn(str(original.pk) + ';', texto)
        self.assertNotIn('Nuevo evento posterior', texto)

    def test_exportacion_por_lotes_no_repite_ni_omite_eventos_con_fecha_igual(self):
        eventos = self.varios(1003)
        Auditoria.objects.update(fecha_creacion=datetime(2026, 10, 27, 15, 30, tzinfo=tz.utc))
        _, _, filas = self.csv()
        self.assertEqual([int(fila[0]) for fila in filas], [e.pk for e in eventos][::-1])

    def test_csv_neutraliza_formulas_en_campos_controlados_por_usuarios(self):
        textos = ['=HYPERLINK("https://example.test")', '+SUM(1,2)', '-1+2', '@SUM(1,2)', '  =1+1', '\t=1+1']
        for texto in textos:
            self.evento(descripcion=texto, user_agent=texto)
        _, cabecera, filas = self.csv()
        for fila, original in zip(filas, textos[::-1]):
            self.assertEqual(fila[cabecera.index('Descripción')], "'" + original)
            self.assertEqual(fila[cabecera.index('Navegador / dispositivo')], "'" + original)

    def test_reporte_imprimible_completo_escapa_html_y_muestra_filtros(self):
        texto = '<script>alert("x")</script>\nDescripción completa de SKU: REP-01'
        self.varios(206, descripcion=texto)
        r = self.client.get('/api/v1/auditoria/reporte/', {'modelo': 'Movimiento', 'search': 'REP-01', 'page': 2})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r['Content-Type'].startswith('text/html'))
        self.assertContains(r, '&lt;script&gt;')
        self.assertNotContains(r, '<script>')
        self.assertEqual(r.content.decode().count('class="descripcion"'), 206)
        self.assertContains(r, '<strong>Total:</strong> 206 eventos')
        self.assertContains(r, '<strong>Módulo:</strong> Movimiento')
        self.assertContains(r, 'America/Santiago')
        self.assertEqual(Auditoria.objects.count(), 206)

    def test_historial_y_reportes_vacios(self):
        r = self.client.get('/api/v1/auditoria/historial/')
        self.assertEqual(r.data['count'], 0)
        self.assertEqual(r.data['results'], [])
        meta, _, filas = self.csv()
        self.assertEqual(filas, [])
        self.assertIn(['Total de eventos', '0'], meta)
        self.assertContains(self.client.get('/api/v1/auditoria/reporte/'), 'No hay eventos para estos filtros.')

    def test_listado_no_hace_una_consulta_por_usuario(self):
        self.varios(25)
        with self.assertNumQueries(2):
            r = self.client.get('/api/v1/auditoria/historial/')
        self.assertEqual(len(r.data['results']), 25)
