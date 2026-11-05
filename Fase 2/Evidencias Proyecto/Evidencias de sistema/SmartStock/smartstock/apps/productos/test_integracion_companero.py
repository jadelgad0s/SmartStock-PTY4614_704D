"""Pruebas de integración de los módulos aportados por el compañero."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.usuarios.models import Rol, Usuario, Permiso
from apps.productos.models import (
    Bodega, Producto, StockBodega, CodigoBarra, Notificacion,
)
from apps.productos.serializers import ProductoCreateUpdateSerializer
from apps.productos.views_notificaciones import notificar_administradores


class IntegracionCompaneroTests(TestCase):
    def setUp(self):
        rol_admin = Rol.objects.create(nombre='Administrador', codigo='administrador')
        rol_operador = Rol.objects.create(nombre='Operador', codigo='operador')
        permiso = Permiso.objects.create(
            codigo='registrar_merma', nombre='Registrar mermas',
            modulo='movimientos',
        )
        rol_admin.permisos.add(permiso)
        self.admin = Usuario.objects.create_user(
            email='admin-companero@example.com', password='Password123!',
            nombres='Admin', apellidos='Uno', rol=rol_admin,
        )
        self.segundo_admin = Usuario.objects.create_user(
            email='admin-dos@example.com', password='Password123!',
            nombres='Admin', apellidos='Dos', rol=rol_admin,
        )
        self.operador = Usuario.objects.create_user(
            email='operador-companero@example.com', password='Password123!',
            nombres='Operador', apellidos='Uno', rol=rol_operador,
        )
        self.producto = Producto.objects.create(
            sku='PRUEBA-CODIGO-1', nombre='Producto de prueba',
            precio_referencia='1000.00',
        )
        self.bodega = Bodega.objects.create(
            nombre='Bodega Central', direccion='Casa Matriz', activa=True,
        )
        self.stock = StockBodega.objects.create(
            producto=self.producto, bodega=self.bodega, cantidad_total=10,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_codigo_barra_guardar_y_actualizar_sin_perder_codigo(self):
        serializer = ProductoCreateUpdateSerializer(data={
            'sku': 'COD-UNO', 'nombre': 'Producto nuevo',
            'precio_referencia': '999.99',
            'codigos_barra': [
                {'codigo': '7801234567890', 'tipo': 'BARRA'},
            ],
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        nuevo = serializer.save()
        self.assertEqual(nuevo.codigos_barra.get().codigo, '7801234567890')
        self.assertTrue(nuevo.codigos_barra.get().es_principal)

        actualizado = ProductoCreateUpdateSerializer(nuevo, data={
            'codigos_barra': [{'codigo': '7801234567890', 'tipo': 'BARRA'}],
        }, partial=True)
        self.assertTrue(actualizado.is_valid(), actualizado.errors)
        actualizado.save()
        self.assertEqual(nuevo.codigos_barra.count(), 1)

    def test_rechaza_codigo_duplicado_de_otro_producto(self):
        CodigoBarra.objects.create(producto=self.producto, codigo='123456789', es_principal=True)
        otro = Producto.objects.create(sku='PRUEBA-CODIGO-2', nombre='Otro')
        data = ProductoCreateUpdateSerializer(otro, data={
            'codigos_barra': [{'codigo': '123456789'}],
        }, partial=True)
        self.assertFalse(data.is_valid())
        self.assertIn('codigos_barra', data.errors)

    def test_no_permita_codigos_duplicados_en_un_mismo_formulario(self):
        data = ProductoCreateUpdateSerializer(self.producto, data={
            'codigos_barra': [{'codigo': '111111'}, {'codigo': '111111'}],
        }, partial=True)
        self.assertFalse(data.is_valid())
        self.assertIn('codigos_barra', data.errors)

    def test_notifica_administradores_y_no_operadores(self):
        with self.captureOnCommitCallbacks(execute=True):
            notificar_administradores(
                tipo='MOVIMIENTO', titulo='Entrada de prueba',
                mensaje='Ingreso de producto', link='/movimientos/',
                actor_id=self.admin.id,
            )
        self.assertEqual(Notificacion.objects.count(), 2)
        self.assertEqual(
            set(Notificacion.objects.values_list('usuario_destino_id', flat=True)),
            {self.admin.id, self.segundo_admin.id},
        )

    def test_bandeja_personal_y_sin_acceso_a_avisos_ajenos(self):
        propia = Notificacion.objects.create(
            usuario_destino=self.admin, titulo='Alerta propia', mensaje='Uno',
        )
        ajena = Notificacion.objects.create(
            usuario_destino=self.segundo_admin, titulo='Alerta ajena', mensaje='Dos',
        )
        response = self.client.get('/api/v1/productos/notificaciones/no-leidas/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['total'], 1)
        self.assertEqual(response.data['data']['items'][0]['id'], propia.id)

        self.assertEqual(
            self.client.post(
                f'/api/v1/productos/notificaciones/{ajena.pk}/marcar-leida/'
            ).status_code, 404
        )
        self.assertFalse(Notificacion.objects.get(pk=ajena.pk).leida)

        respuesta = self.client.post(
            f'/api/v1/productos/notificaciones/{propia.pk}/marcar-leida/'
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(Notificacion.objects.get(pk=propia.pk).leida)

    def test_merma_exitosa_crea_avisos_y_error_no_crea_avisos(self):
        payload = {
            'producto_id': self.producto.pk, 'cantidad': 2,
            'motivo': 'DAÑO', 'observacion': 'Envase abierto.',
        }
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post('/api/v1/productos/mermas/', payload, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(Notificacion.objects.filter(tipo='MERMA').count(), 2)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post('/api/v1/productos/mermas/', {
                **payload, 'cantidad': 1000,
            }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Notificacion.objects.filter(tipo='MERMA').count(), 2)

    def test_no_autenticado_no_puede_ver_notificaciones(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get('/api/v1/productos/notificaciones/no-leidas/').status_code,
            401,
        )
