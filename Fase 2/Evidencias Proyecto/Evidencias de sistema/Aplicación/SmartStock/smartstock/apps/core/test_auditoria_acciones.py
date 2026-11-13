"""Acciones de activación y baja, incluidas las clasificaciones históricas."""
import csv
import io

from django.test import TestCase
from rest_framework.test import APIClient

from apps.productos.models import Producto, StockBodega, StockMinimo, Bodega
from apps.usuarios.models import Permiso, Rol, Usuario
from .models import Auditoria

ROOT = '/api/v1/auditoria/'


class AuditoriaAccionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol = Rol.objects.create(nombre='Administrador', codigo='administrador')
        for codigo in ('editar_producto', 'eliminar_producto'):
            cls.rol.permisos.add(Permiso.objects.create(codigo=codigo, nombre=codigo, modulo='productos'))
        cls.admin = Usuario.objects.create_user(email='acciones-admin@example.com', nombres='Admin', apellidos='Auditoría', rol=cls.rol)
        cls.usuario = Usuario.objects.create_user(email='acciones-usuario@example.com', nombres='Persona', apellidos='Prueba')
        cls.producto = Producto.objects.create(sku='AUD-01', nombre='Producto de auditoría')
        cls.bodega = Bodega.objects.create(nombre='Bodega Central', direccion='Central')
        StockBodega.objects.create(producto=cls.producto, bodega=cls.bodega, cantidad_total=3)

    def setUp(self):
        self.client = APIClient(); self.client.force_authenticate(self.admin)

    def evento(self, **datos):
        return Auditoria.objects.create(**{
            'usuario': self.admin, 'accion': 'DELETE', 'modelo': 'Producto',
            'objeto_id': str(self.producto.pk), 'descripcion': 'Producto desactivado: AUD-01',
            'ip_address': '192.0.2.10', 'user_agent': 'Navegador de prueba',
            **datos,
        })

    def historial(self, **filtros):
        r = self.client.get(ROOT + 'historial/', filtros)
        self.assertEqual(r.status_code, 200, r.data)
        return r.data

    def csv(self, **filtros):
        r = self.client.get(ROOT + 'exportar/', filtros)
        self.assertEqual(r.status_code, 200)
        filas = list(csv.reader(io.StringIO(b''.join(r.streaming_content).decode('utf-8-sig')), delimiter=';'))
        indice = next(i for i, f in enumerate(filas) if f and f[0] == 'ID')
        return filas[:indice], filas[indice], filas[indice + 1:]

    def test_historial_clasifica_desactivaciones_antiguas_de_usuario_producto_y_rol(self):
        for modelo, descripcion in (('Usuario', 'Usuario desactivado: persona@example.com'),
                                    ('Producto', 'Producto desactivado: AUD-01'), ('Rol', 'Rol desactivado: Operador')):
            with self.subTest(modelo=modelo):
                e = self.evento(modelo=modelo, descripcion=descripcion)
                datos = self.historial(modelo=modelo)['results'][0]
                self.assertEqual((datos['id'], datos['accion'], datos['accion_etiqueta']), (e.pk, 'DEACTIVATE', 'Desactivación'))

    def test_historial_clasifica_reactivaciones_antiguas_de_producto_y_usuario(self):
        for modelo, descripcion in (('Usuario', 'Usuario reactivado: persona@example.com'), ('Producto', 'Producto reactivado: AUD-01')):
            self.evento(accion='UPDATE', modelo=modelo, descripcion=descripcion)
        datos = self.historial()['results']
        self.assertTrue(all(e['accion'] == 'REACTIVATE' and e['accion_etiqueta'] == 'Reactivación' for e in datos))

    def test_nuevos_codigos_y_eliminacion_definitiva_tienen_etiquetas_propias(self):
        for accion, etiqueta in (('DEACTIVATE', 'Desactivación'), ('REACTIVATE', 'Reactivación'), ('DELETE', 'Eliminación definitiva')):
            e = self.evento(accion=accion, descripcion='Operación registrada con código explícito')
            e.full_clean()
            self.assertEqual(e.get_accion_display(), etiqueta)
            self.assertEqual(self.historial()['results'][0]['accion_etiqueta'], etiqueta)

    def test_desactivaciones_nuevas_y_antiguas_se_filtran_antes_de_paginar(self):
        eventos = [self.evento(accion='DELETE' if i % 2 else 'DEACTIVATE') for i in range(34)]
        self.evento(descripcion='Producto eliminado definitivamente: OTRO')
        ids = []
        for pagina, cantidad in ((1, 25), (2, 9)):
            d = self.historial(accion='DEACTIVATE', modelo='producto', usuario=self.admin.pk, search='AUD-01', page=pagina)
            self.assertEqual(d['count'], 34); self.assertEqual(len(d['results']), cantidad)
            ids.extend(e['id'] for e in d['results'])
        self.assertEqual(ids, [e.pk for e in eventos][::-1])

    def test_filtro_eliminacion_excluye_las_desactivaciones_historicas(self):
        self.evento(); real = self.evento(descripcion='Producto eliminado definitivamente: AUD-01')
        d = self.historial(accion='DELETE')
        self.assertEqual([e['id'] for e in d['results']], [real.pk])
        self.assertEqual(d['results'][0]['accion_etiqueta'], 'Eliminación definitiva')

    def test_filtro_modificacion_excluye_reactivaciones_y_el_filtro_reactivacion_incluye_ambas_epocas(self):
        modificacion = self.evento(accion='UPDATE', descripcion='Producto actualizado: AUD-01')
        anterior = self.evento(accion='UPDATE', descripcion='Producto reactivado: AUD-01')
        nueva = self.evento(accion='REACTIVATE', descripcion='Producto reactivado: AUD-01')
        self.assertEqual([e['id'] for e in self.historial(accion='UPDATE')['results']], [modificacion.pk])
        self.assertEqual([e['id'] for e in self.historial(accion='reactivate')['results']], [nueva.pk, anterior.pk])

    def test_no_infiere_acciones_a_partir_de_textos_ambiguos_o_modulos_distintos(self):
        casos = [
            ('DELETE', 'Usuario', 'Observación: Usuario desactivado: persona@example.com'),
            ('DELETE', 'Producto', 'Usuario desactivado: texto en otro módulo'),
            ('UPDATE', 'Producto', 'Producto actualizado: contiene la palabra reactivado'),
            ('CREATE', 'Usuario', 'Usuario desactivado: texto de creación'),
            ('CUSTOM', 'Producto', 'Producto desactivado: evento personalizado'),
        ]
        for accion, modelo, descripcion in casos:
            e = self.evento(accion=accion, modelo=modelo, descripcion=descripcion)
            self.assertEqual(self.client.get(ROOT + str(e.pk) + '/').data['data']['accion'], accion)

    def test_clasificacion_historica_acepta_variaciones_de_mayusculas(self):
        self.evento(accion='delete', modelo='usuario', descripcion='USUARIO DESACTIVADO: persona@example.com')
        self.assertEqual(self.historial()['results'][0]['accion'], 'DEACTIVATE')

    def test_detalle_muestra_la_clasificacion_y_conserva_el_codigo_registrado(self):
        e = self.evento()
        d = self.client.get(f'{ROOT}{e.pk}/').data['data']
        self.assertEqual((d['accion'], d['accion_etiqueta'], d['accion_registrada']), ('DEACTIVATE', 'Desactivación', 'DELETE'))
        self.assertEqual(d['ip_address'], '192.0.2.10'); self.assertEqual(d['objeto_id'], str(self.producto.pk))
        self.assertEqual(d['descripcion'], 'Producto desactivado: AUD-01')

    def test_consultar_filtrar_y_exportar_no_reescribe_registros_historicos(self):
        self.evento(); self.evento(accion='UPDATE', descripcion='Producto reactivado: AUD-01')
        antes = list(Auditoria.objects.order_by('pk').values())
        self.historial(); self.historial(accion='DEACTIVATE'); self.csv(accion='REACTIVATE')
        self.client.get(ROOT + 'opciones/'); self.client.get(ROOT + 'reporte/'); self.client.get(ROOT)
        self.assertEqual(list(Auditoria.objects.order_by('pk').values()), antes)

    def test_opciones_exponen_las_tres_acciones_con_nombres_distintos(self):
        opciones = self.client.get(ROOT + 'opciones/').data['data']['acciones']
        for valor, etiqueta in (('DEACTIVATE', 'Desactivación'), ('REACTIVATE', 'Reactivación'), ('DELETE', 'Eliminación definitiva')):
            self.assertIn({'valor': valor, 'etiqueta': etiqueta}, opciones)

    def test_csv_filtra_la_accion_clasificada_y_conserva_ambos_codigos(self):
        antiguo = self.evento(); nuevo = self.evento(accion='DEACTIVATE')
        self.evento(descripcion='Producto eliminado definitivamente: Otro')
        meta, cabecera, filas = self.csv(accion='deactivate')
        self.assertIn(['Acción', 'Desactivación'], meta)
        self.assertEqual([int(f[0]) for f in filas], [nuevo.pk, antiguo.pk])
        self.assertEqual([f[cabecera.index('Acción')] for f in filas], ['Desactivación'] * 2)
        self.assertEqual([f[cabecera.index('Código de acción')] for f in filas], ['DEACTIVATE'] * 2)
        self.assertEqual([f[cabecera.index('Código registrado')] for f in filas], ['DEACTIVATE', 'DELETE'])

    def test_reporte_imprimible_distingue_acciones_y_colores(self):
        self.evento(); self.evento(accion='UPDATE', descripcion='Producto reactivado: AUD-01')
        self.evento(descripcion='Producto eliminado definitivamente: AUD-02')
        r = self.client.get(ROOT + 'reporte/')
        for clase, etiqueta in (('deactivate', 'Desactivación'), ('reactivate', 'Reactivación'), ('delete', 'Eliminación definitiva')):
            self.assertContains(r, f'class="accion accion-{clase}">{etiqueta}</span>')
        r = self.client.get(ROOT + 'reporte/', {'accion': 'REACTIVATE'})
        self.assertContains(r, '<strong>Total:</strong> 1 eventos')
        self.assertNotContains(r, 'Producto desactivado: AUD-01')

    def test_endpoint_anterior_conserva_sus_campos_y_distingue_la_desactivacion(self):
        self.evento()
        e = self.client.get(ROOT).data['data'][0]
        self.assertEqual(set(e), {'fecha', 'usuario', 'accion', 'modelo', 'descripcion'})
        self.assertEqual(e['accion'], 'DEACTIVATE')

    def test_producto_guarda_desactivacion_y_reactivacion_sin_confundir_edicion(self):
        ruta = f'/api/v1/productos/{self.producto.pk}/'
        for _ in range(2): self.assertEqual(self.client.delete(ruta).status_code, 200)
        for _ in range(2): self.assertEqual(self.client.post(ruta + 'activar/').status_code, 200)
        self.assertEqual(self.client.patch(ruta, {'nombre': 'Nombre nuevo'}, format='json').status_code, 200)
        self.assertEqual(list(Auditoria.objects.order_by('pk').values_list('accion', flat=True)), ['DEACTIVATE', 'REACTIVATE', 'UPDATE'])

    def test_usuario_guarda_desactivacion_reactivacion_y_eliminacion_real(self):
        ruta = f'/api/v1/usuarios/{self.usuario.pk}/'
        for _ in range(2): self.assertEqual(self.client.delete(ruta).status_code, 200)
        for _ in range(2): self.assertEqual(self.client.post(ruta + 'activar/').status_code, 200)
        self.assertEqual(self.client.delete(ruta + 'eliminar-definitivamente/').status_code, 200)
        self.assertEqual(list(Auditoria.objects.order_by('pk').values_list('accion', flat=True)), ['DEACTIVATE', 'REACTIVATE', 'DELETE'])

    def test_producto_eliminado_definitivamente_conserva_delete(self):
        p = Producto.objects.create(sku='AUD-LIBRE', nombre='Sin referencias')
        r = self.client.delete(f'/api/v1/productos/{p.pk}/eliminar-definitivamente/')
        self.assertEqual(r.status_code, 200, r.data)
        e = Auditoria.objects.get(); self.assertEqual(e.accion, 'DELETE')
        self.assertEqual(self.historial()['results'][0]['accion_etiqueta'], 'Eliminación definitiva')

    def test_baja_de_rol_tambien_es_desactivacion(self):
        rol = Rol.objects.create(codigo='rol_libre', nombre='Sin usuarios')
        r = self.client.delete(f'/api/v1/usuarios/roles/{rol.pk}/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Auditoria.objects.get().accion, 'DEACTIVATE')

    def test_cambio_de_minimo_sigue_siendo_modificacion(self):
        r = self.client.patch(f'/api/v1/productos/{self.producto.pk}/stock-minimo/', {'bodega': self.bodega.pk, 'cantidad_minima': 5}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Auditoria.objects.get().accion, 'UPDATE')
        self.assertEqual(StockMinimo.objects.get().cantidad_minima, 5)
