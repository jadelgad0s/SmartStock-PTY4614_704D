"""Pruebas de integración para bajas reales de inventario."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.productos.models import Bodega, Merma, Producto, StockBodega
from apps.usuarios.models import Permiso, Rol, Usuario


class MermasApiTests(TestCase):
    def setUp(self):
        self.rol = Rol.objects.create(nombre='Administrador', codigo='administrador')
        permiso = Permiso.objects.create(
            codigo='registrar_merma', nombre='Registrar mermas',
            descripcion='Dar de baja stock', modulo='movimientos',
        )
        self.rol.permisos.add(permiso)
        self.admin = Usuario.objects.create_user(
            email='prueba-mermas@example.com',
            password='UnPasswordSeguro123!',
            nombres='Persona', apellidos='Prueba',
            rol=self.rol,
        )
        self.bodega = Bodega.objects.create(
            nombre='Bodega Central', direccion='Casa Matriz', activa=True,
        )
        self.producto = Producto.objects.create(
            sku='SKU-PRUEBA-1', nombre='Producto para mermas',
            precio_referencia='1000.00',
        )
        self.stock = StockBodega.objects.create(
            producto=self.producto, bodega=self.bodega, cantidad_total=10,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.url = '/api/v1/productos/mermas/'

    def payload(self, **cambios):
        data = {
            'producto_id': self.producto.pk,
            'cantidad': 3,
            'motivo': 'DAÑO',
            'observacion': 'Embalaje deteriorado.',
        }
        data.update(cambios)
        return data

    def test_registra_merma_descuenta_stock_y_guarda_auditoria(self):
        respuesta = self.client.post(self.url, self.payload(), format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 7)
        self.assertEqual(respuesta.data['data']['stock_restante'], 7)
        merma = Merma.objects.get()
        self.assertEqual(merma.cantidad, 3)
        self.assertEqual(merma.motivo.descripcion, 'Daño en Bodega')
        self.assertEqual(merma.observacion, 'Embalaje deteriorado.')
        self.assertEqual(merma.usuario, self.admin)
        self.assertEqual(merma.bodega, self.bodega)
        self.assertTrue(Auditoria.objects.filter(modelo='Merma', objeto_id=str(merma.pk)).exists())

    def test_cantidad_superior_al_stock_no_modifica_nada(self):
        respuesta = self.client.post(self.url, self.payload(cantidad=11), format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 10)
        self.assertEqual(Merma.objects.count(), 0)

    def test_cantidad_cero_y_negativa_son_rechazadas(self):
        for cantidad in (0, -1):
            with self.subTest(cantidad=cantidad):
                res = self.client.post(self.url, self.payload(cantidad=cantidad), format='json')
                self.assertEqual(res.status_code, 400)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 10)
        self.assertFalse(Merma.objects.exists())

    def test_producto_inexistente_y_motivo_invalido(self):
        res = self.client.post(self.url, self.payload(producto_id=999999), format='json')
        self.assertEqual(res.status_code, 404)
        res = self.client.post(self.url, self.payload(motivo='NO_VALIDO'), format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Merma.objects.exists())

    def test_sin_stock_en_bodega_central(self):
        self.stock.delete()
        res = self.client.post(self.url, self.payload(), format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Merma.objects.exists())

    def test_operador_no_puede_crear_ni_ver_mermas(self):
        operador = Rol.objects.create(nombre='Operador', codigo='operador')
        usuario = Usuario.objects.create_user(
            email='operador-merma@example.com', password='OtroPassword123!',
            nombres='Operador', apellidos='Prueba', rol=operador,
        )
        self.client.force_authenticate(user=usuario)
        self.assertEqual(self.client.post(self.url, self.payload(), format='json').status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.cantidad_total, 10)

    def test_historico_devuelve_las_mermas_guardadas(self):
        self.client.post(self.url, self.payload(), format='json')
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.data['data']), 1)
        self.assertEqual(respuesta.data['data'][0]['producto'], self.producto.nombre)
        self.assertEqual(respuesta.data['data'][0]['motivo'], 'Daño en Bodega')
        self.assertEqual(respuesta.data['data'][0]['observacion'], 'Embalaje deteriorado.')

    def test_no_autenticado_recibe_401(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.client.post(self.url, self.payload(), format='json').status_code, 401)
