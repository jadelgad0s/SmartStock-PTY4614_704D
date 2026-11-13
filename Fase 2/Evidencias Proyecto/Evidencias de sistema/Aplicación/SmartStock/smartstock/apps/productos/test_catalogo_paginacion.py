"""Pruebas de paginación, búsqueda y ordenamiento del catálogo de productos."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.productos.models import CodigoBarra, Producto
from apps.usuarios.models import Permiso, Rol, Usuario


class CatalogoPaginacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        rol = Rol.objects.create(nombre='Operador', codigo='operador')
        rol.permisos.add(Permiso.objects.create(codigo='ver_producto', nombre='Ver productos', modulo='productos'))
        cls.usuario = Usuario.objects.create_user(
            email='catalogo-test@example.com',
            password='PasswordSeguro123!',
            nombres='Operador', apellidos='Pruebas', rol=rol,
        )
        ahora = timezone.now()
        for i in range(55):
            producto = Producto.objects.create(
                sku=f'CAT-{i:03d}',
                nombre=f'Producto {i:03d}',
                precio_referencia=Decimal(55000 - i * 100),
            )
            # Controlar la fecha para verificar ambos órdenes sin depender del reloj.
            Producto.objects.filter(pk=producto.pk).update(
                fecha_creacion=ahora - timedelta(days=55 - i),
            )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)

    def test_25_por_pagina_y_todas_las_paginas(self):
        ids = []
        for pagina, esperado in ((1, 25), (2, 25), (3, 5)):
            respuesta = self.client.get('/api/v1/productos/', {'page': pagina})
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.data['count'], 55)
            self.assertEqual(len(respuesta.data['results']), esperado)
            ids.extend(p['id'] for p in respuesta.data['results'])
        self.assertEqual(len(ids), 55)
        self.assertEqual(len(set(ids)), 55)

    def test_no_autenticado_no_consulta_catalogo(self):
        self.client.force_authenticate(user=None)
        respuesta = self.client.get('/api/v1/productos/')
        self.assertEqual(respuesta.status_code, 401)

    def test_busqueda_en_todo_el_catalogo_no_solo_primera_pagina(self):
        respuesta = self.client.get('/api/v1/productos/', {
            'search': 'Producto 054',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 1)
        self.assertEqual(respuesta.data['results'][0]['sku'], 'CAT-054')

    def test_busqueda_usa_paginas_y_ordenamiento(self):
        respuesta = self.client.get('/api/v1/productos/', {
            'search': 'Producto',
            'page': 2,
            'ordering': '-nombre,-id',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 55)
        self.assertEqual(respuesta.data['results'][0]['sku'], 'CAT-029')

    def test_seis_tipos_de_ordenamiento(self):
        ordenes = {
            'nombre,id': ('CAT-000', 'CAT-001'),
            '-nombre,-id': ('CAT-054', 'CAT-053'),
            'precio_referencia,id': ('CAT-054', 'CAT-053'),
            '-precio_referencia,-id': ('CAT-000', 'CAT-001'),
            'fecha_creacion,id': ('CAT-000', 'CAT-001'),
            '-fecha_creacion,-id': ('CAT-054', 'CAT-053'),
        }
        for orden, skus in ordenes.items():
            with self.subTest(orden=orden):
                respuesta = self.client.get('/api/v1/productos/', {
                    'ordering': orden,
                })
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(
                    tuple(p['sku'] for p in respuesta.data['results'][:2]),
                    skus,
                )

    def test_filtros_por_codigo_de_barras_no_duplican_productos(self):
        producto = Producto.objects.get(sku='CAT-054')
        CodigoBarra.objects.create(producto=producto, codigo='CODIGO-UNICO-54')
        CodigoBarra.objects.create(producto=producto, codigo='OTRO-UNICO-54')
        respuesta = self.client.get('/api/v1/productos/', {
            'search': 'UNICO-54',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 1)
        self.assertEqual(respuesta.data['results'][0]['sku'], 'CAT-054')

    def test_tamano_de_pagina_no_se_modifica_desde_la_url(self):
        respuesta = self.client.get('/api/v1/productos/', {'page_size': 100})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.data['results']), 25)

    def test_ordenes_desempatan_por_id_entre_paginas(self):
        ids = []
        for i in range(30):
            producto = Producto.objects.create(
                sku=f'EMP-{i:03d}', nombre='Empate',
                precio_referencia=Decimal('1000'),
            )
            ids.append(producto.id)
        Producto.objects.filter(id__in=ids).update(fecha_creacion=timezone.now())

        for orden in (
            'nombre,id', '-nombre,-id',
            'precio_referencia,id', '-precio_referencia,-id',
            'fecha_creacion,id', '-fecha_creacion,-id',
        ):
            with self.subTest(orden=orden):
                encontrados = []
                for pagina in (1, 2):
                    respuesta = self.client.get('/api/v1/productos/', {
                        'search': 'Empate', 'ordering': orden, 'page': pagina,
                    })
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertEqual(respuesta.data['count'], 30)
                    encontrados.extend(p['id'] for p in respuesta.data['results'])
                self.assertEqual(
                    encontrados, sorted(ids, reverse=orden.startswith('-')),
                )

    def test_pagina_inexistente_y_recuperacion_en_ultima_pagina(self):
        Producto.objects.filter(sku__gte='CAT-050').delete()
        respuesta = self.client.get('/api/v1/productos/', {'page': 3})
        self.assertEqual(respuesta.status_code, 404)

        respuesta = self.client.get('/api/v1/productos/', {'page': 'last'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 50)
        self.assertEqual(len(respuesta.data['results']), 25)
        self.assertEqual(respuesta.data['results'][0]['sku'], 'CAT-025')

    def test_ultima_pagina_respeta_busqueda_y_orden(self):
        respuesta = self.client.get('/api/v1/productos/', {
            'page': 'last', 'search': 'Producto', 'ordering': '-nombre,-id',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.data['results']), 5)
        self.assertEqual(respuesta.data['results'][0]['sku'], 'CAT-004')

    def test_sin_coincidencias_y_catalogo_vacio(self):
        respuesta = self.client.get('/api/v1/productos/', {'search': 'inexistente'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 0)
        self.assertEqual(respuesta.data['results'], [])

        Producto.objects.all().delete()
        respuesta = self.client.get('/api/v1/productos/', {'page': 'last'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 0)
        self.assertEqual(respuesta.data['results'], [])

    def test_inactivos_se_pueden_encontrar_y_filtrar_para_reactivar(self):
        Producto.objects.filter(sku='CAT-054').update(activo=False)
        respuesta = self.client.get('/api/v1/productos/', {'search': 'CAT-054'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 1)
        self.assertFalse(respuesta.data['results'][0]['activo'])

        respuesta = self.client.get('/api/v1/productos/', {
            'search': 'CAT-054', 'activo': 'true',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 0)

