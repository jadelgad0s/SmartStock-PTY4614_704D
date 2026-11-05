"""No permitir que la papelera afecte historial ni cuentas administrativas."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.usuarios.models import Rol, Usuario
from apps.productos.models import Producto, StockBodega, Bodega


class AccionesSegurasTests(TestCase):
    def setUp(self):
        self.admin_rol = Rol.objects.create(nombre='Administrador', codigo='administrador')
        self.operador_rol = Rol.objects.create(nombre='Operador', codigo='operador')
        self.admin = Usuario.objects.create_user(
            email='admin-acciones@example.com', password='Pass123456!',
            nombres='Admin', apellidos='Acciones', rol=self.admin_rol
        )
        self.admin2 = Usuario.objects.create_user(
            email='admin-otro@example.com', password='Pass123456!',
            nombres='Admin', apellidos='Segundo', rol=self.admin_rol
        )
        self.operador = Usuario.objects.create_user(
            email='operador-acciones@example.com', password='Pass123456!',
            nombres='Operador', apellidos='Acciones', rol=self.operador_rol
        )
        self.cliente = APIClient()
        self.cliente.force_authenticate(user=self.admin)

    def test_administrador_no_puede_desactivar_otro_administrador(self):
        resultado = self.cliente.delete(f'/api/v1/usuarios/{self.admin2.id}/')
        self.assertEqual(resultado.status_code, 403, resultado.data)
        self.admin2.refresh_from_db()
        self.assertTrue(self.admin2.activo)

    def test_administrador_no_puede_eliminar_a_otro_administrador_ni_a_si_mismo(self):
        for id_usuario in [self.admin.id, self.admin2.id]:
            respuesta = self.cliente.delete(
                f'/api/v1/usuarios/{id_usuario}/eliminar-definitivamente/'
            )
            self.assertEqual(respuesta.status_code, 403, respuesta.data)
            self.assertTrue(Usuario.objects.filter(pk=id_usuario).exists())

    def test_no_se_puede_cambiar_el_rol_de_un_administrador(self):
        r = self.cliente.patch(f'/api/v1/usuarios/{self.admin2.id}/', {
            'rol_id': self.operador_rol.pk,
        }, format='json')
        self.assertEqual(r.status_code, 403, r.data)
        self.admin2.refresh_from_db()
        self.assertEqual(self.admin2.rol_id, self.admin_rol.id)

    def test_operador_no_puede_acceder_ni_borrar_usuarios(self):
        self.cliente.force_authenticate(user=self.operador)
        self.assertEqual(self.cliente.get('/api/v1/usuarios/').status_code, 403)
        self.assertEqual(self.cliente.delete(
            f'/api/v1/usuarios/{self.admin2.id}/eliminar-definitivamente/'
        ).status_code, 403)

    def test_administrador_puede_eliminar_usuario_nuevo_sin_historial(self):
        extra = Usuario.objects.create_user(
            email='sin-historial@example.com', password='Pass123456!',
            nombres='Nuevo', apellidos='Usuario', rol=self.operador_rol
        )
        respuesta = self.cliente.delete(
            f'/api/v1/usuarios/{extra.pk}/eliminar-definitivamente/'
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertFalse(Usuario.objects.filter(pk=extra.pk).exists())

    def test_usuario_con_historial_no_se_puede_eliminar(self):
        from apps.core.models import Auditoria
        Auditoria.objects.create(
            usuario=self.operador, accion='LOGIN',
            modelo='Usuario', objeto_id=str(self.operador.id)
        )
        respuesta = self.cliente.delete(
            f'/api/v1/usuarios/{self.operador.pk}/eliminar-definitivamente/'
        )
        self.assertEqual(respuesta.status_code, 409, respuesta.data)
        self.assertTrue(Usuario.objects.filter(pk=self.operador.id).exists())

    def test_producto_con_stock_no_se_borra_permanentemente(self):
        producto = Producto.objects.create(sku='TEST-PROTEGIDO', nombre='Producto con stock')
        bodega = Bodega.objects.create(nombre='Central', direccion='Central')
        StockBodega.objects.create(producto=producto, bodega=bodega, cantidad_total=5)
        respuesta = self.cliente.delete(
            f'/api/v1/productos/{producto.pk}/eliminar-definitivamente/'
        )
        self.assertEqual(respuesta.status_code, 409, respuesta.data)
        self.assertTrue(Producto.objects.filter(pk=producto.id).exists())

    def test_producto_sin_referencias_si_puede_eliminarse(self):
        producto = Producto.objects.create(sku='TEST-SIN-REFERENCIAS', nombre='Prueba')
        respuesta = self.cliente.delete(
            f'/api/v1/productos/{producto.pk}/eliminar-definitivamente/'
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertFalse(Producto.objects.filter(pk=producto.id).exists())

    def test_producto_nuevo_con_codigo_barra_puede_eliminarse(self):
        from apps.productos.models import CodigoBarra
        producto = Producto.objects.create(sku='TEST-CODIGO-NUEVO', nombre='Nuevo con barcode')
        CodigoBarra.objects.create(producto=producto, codigo='7800001234567', es_principal=True)
        respuesta = self.cliente.delete(
            f'/api/v1/productos/{producto.pk}/eliminar-definitivamente/'
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertFalse(Producto.objects.filter(pk=producto.id).exists())
        self.assertFalse(CodigoBarra.objects.filter(codigo='7800001234567').exists())

    def test_operador_no_puede_eliminar_productos_definitivamente(self):
        producto = Producto.objects.create(sku='TEST-OPERADOR', nombre='Prueba')
        self.cliente.force_authenticate(user=self.operador)
        respuesta = self.cliente.delete(
            f'/api/v1/productos/{producto.pk}/eliminar-definitivamente/'
        )
        self.assertEqual(respuesta.status_code, 403, respuesta.data)
        self.assertTrue(Producto.objects.filter(pk=producto.id).exists())
