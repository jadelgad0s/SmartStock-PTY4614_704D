"""Stock conservado, confirmaciones repetidas y consulta de transferencias."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
import uuid

from django.db import close_old_connections, connection, connections
from django.db.models import QuerySet, Sum
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.usuarios.models import Permiso, Rol, Usuario
from .models import (
    Bodega, CodigoBarra, DetalleMovimiento, DetalleTransferencia, HistorialMovimientos,
    EnvioAlertaSMS, EstadoStockSMS, Merma, Movimiento, Notificacion, Producto, StockBodega, StockMinimo, Transferencia,
)

ROOT = '/api/v1/productos/transferencias/'


def usuario_transferencias(email='transferencias@example.com'):
    rol, _ = Rol.objects.get_or_create(codigo='encargado_bodega', defaults={'nombre': 'Encargado de bodega'})
    permiso, _ = Permiso.objects.get_or_create(codigo='registrar_transferencia', defaults={'nombre': 'Registrar transferencias', 'modulo': 'movimientos'})
    rol.permisos.add(permiso)
    return Usuario.objects.create_user(email=email, nombres='Persona', apellidos='Transferencias', rol=rol)


@override_settings(SMS_ALERTAS_ACTIVAS=False)
class TransferenciasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = usuario_transferencias()
        cls.admin = Usuario.objects.create_superuser(email='admin-transferencias@example.com', nombres='Admin', apellidos='Prueba')
        cls.origen = Bodega.objects.create(nombre='Bodega Central')
        cls.destino = Bodega.objects.create(nombre='Bodega Norte')
        cls.tercera = Bodega.objects.create(nombre='Tercera bodega')
        cls.producto = Producto.objects.create(sku='TR-001', nombre='Bebida de prueba')
        cls.stock_origen = StockBodega.objects.create(producto=cls.producto, bodega=cls.origen, cantidad_total=24)
        cls.stock_destino = StockBodega.objects.create(producto=cls.producto, bodega=cls.destino, cantidad_total=6)
        StockBodega.objects.create(producto=cls.producto, bodega=cls.tercera, cantidad_total=20)
        CodigoBarra.objects.create(producto=cls.producto, codigo='4006381333931', es_principal=True)
        CodigoBarra.objects.create(producto=cls.producto, codigo='COD/SECUNDARIO', tipo='QR')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)
        self.solicitud = str(uuid.uuid4())

    def datos(self, **cambios):
        return {'bodega_origen_id': self.origen.pk, 'bodega_destino_id': self.destino.pk,
                'producto_id': self.producto.pk, 'cantidad': 6, 'solicitud_id': self.solicitud, **cambios}

    def registrar(self, **cambios):
        return self.client.post(ROOT, self.datos(**cambios), format='json')

    def consultar(self, ruta='', **params):
        return self.client.get(ROOT + ruta, params)

    def comprobar_sin_cambios(self):
        self.stock_origen.refresh_from_db(); self.stock_destino.refresh_from_db()
        self.assertEqual((self.stock_origen.cantidad_total, self.stock_destino.cantidad_total), (24, 6))
        for modelo in (Transferencia, DetalleTransferencia, Movimiento, DetalleMovimiento, HistorialMovimientos, Auditoria, Notificacion):
            self.assertFalse(modelo.objects.exists(), modelo.__name__)

    def test_traslado_conserva_total_y_registra_dos_movimientos_historial_auditoria_campana(self):
        respuesta = self.registrar()
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.stock_origen.refresh_from_db(); self.stock_destino.refresh_from_db()
        self.assertEqual((self.stock_origen.cantidad_total, self.stock_destino.cantidad_total), (18, 12))
        self.assertEqual(StockBodega.objects.aggregate(n=Sum('cantidad_total'))['n'], 50)
        transferencia = Transferencia.objects.get()
        self.assertEqual(transferencia.estado, 'COMPLETADA')
        self.assertEqual(transferencia.usuario, self.usuario)
        self.assertEqual(transferencia.detalles.get().cantidad, 6)
        self.assertEqual(Movimiento.objects.count(), 2)
        for bodega, operacion in ((self.origen, '-'), (self.destino, '+')):
            movimiento = Movimiento.objects.get(bodega=bodega)
            self.assertEqual(movimiento.tipo.operacion, operacion)
            self.assertEqual(movimiento.detalles.get().cantidad, 6)
            self.assertTrue(movimiento.documento_referencia.startswith(f'Transferencia #{transferencia.pk}:'))
        self.assertEqual(HistorialMovimientos.objects.get().registro_id, transferencia.pk)
        self.assertEqual(Auditoria.objects.get().modelo, 'Transferencia')
        self.assertEqual(set(Notificacion.objects.values_list('usuario_destino_id', flat=True)), {self.usuario.pk, self.admin.pk})
        self.assertTrue(all(n.link == '/transferencias/' for n in Notificacion.objects.all()))
        self.assertEqual(respuesta.data['data']['stock'], {'origen_anterior': 24, 'origen_posterior': 18, 'destino_anterior': 6, 'destino_posterior': 12})

    def test_una_confirmacion_repetida_devuelve_la_misma_transferencia_sin_descontar(self):
        with patch('apps.productos.views_transferencias.evaluar_alerta_sms') as sms:
            primera = self.registrar()
            segunda = self.registrar()
        self.assertEqual((primera.status_code, segunda.status_code), (201, 200))
        self.assertEqual(primera.data['data'], segunda.data['data'])
        self.assertEqual(Transferencia.objects.count(), 1)
        self.assertEqual(Movimiento.objects.count(), 2)
        self.assertEqual(Auditoria.objects.count(), 1)
        self.assertEqual(HistorialMovimientos.objects.count(), 1)
        self.assertEqual(sms.call_count, 2)
        self.assertEqual(StockBodega.objects.get(pk=self.stock_origen.pk).cantidad_total, 18)

    @override_settings(SMS_ALERTAS_ACTIVAS=True, SMS_ALERTAS_DESTINATARIOS=['+56900000001'])
    def test_salida_activa_alerta_y_entrada_recupera_ciclo_sms_despues_del_commit(self):
        from .alertas_sms import evaluar_alerta_sms
        StockMinimo.objects.create(producto=self.producto, bodega=self.origen, cantidad_minima=20)
        StockMinimo.objects.create(producto=self.producto, bodega=self.destino, cantidad_minima=10)
        with patch('apps.productos.alertas_sms.enviar_alerta_sms') as enviar:
            evaluar_alerta_sms(self.producto, self.destino)
            pendiente = EnvioAlertaSMS.objects.get(bodega=self.destino)
            ciclo = EstadoStockSMS.objects.get(bodega=self.destino).ciclo
            with self.captureOnCommitCallbacks(execute=True):
                r = self.registrar()
                self.assertEqual(r.status_code, 201)
                enviar.assert_not_called()
            envio_origen = EnvioAlertaSMS.objects.get(bodega=self.origen)
            enviar.assert_called_once_with(envio_origen.pk)
        self.assertEqual(envio_origen.cantidad, 18)
        self.assertEqual(envio_origen.minimo, 20)
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado, 'CANCELADO')
        recuperado = EstadoStockSMS.objects.get(bodega=self.destino)
        self.assertEqual(recuperado.nivel_maximo, 0)
        self.assertNotEqual(recuperado.ciclo, ciclo)

    def test_clave_reutilizada_con_otro_contenido_se_rechaza(self):
        self.assertEqual(self.registrar().status_code, 201)
        for cambios in ({'cantidad': 5}, {'bodega_destino_id': self.tercera.pk}, {'producto_id': 999999}):
            r = self.registrar(**cambios)
            self.assertEqual(r.status_code, 409, r.data)
            self.assertEqual(r.data['errores']['codigo'], 'SOLICITUD_UTILIZADA')
        self.assertEqual(Transferencia.objects.count(), 1)
        self.assertEqual(StockBodega.objects.get(pk=self.stock_origen.pk).cantidad_total, 18)

    def test_una_nueva_clave_registra_otra_operacion_y_las_claves_se_separan_por_usuario(self):
        self.assertEqual(self.registrar().status_code, 201)
        self.assertEqual(self.registrar(solicitud_id=str(uuid.uuid4())).status_code, 201)
        otro = usuario_transferencias('otra-persona@example.com')
        self.client.force_authenticate(otro)
        self.assertEqual(self.registrar().status_code, 201)
        self.assertEqual(Transferencia.objects.count(), 3)
        self.assertEqual(StockBodega.objects.get(pk=self.stock_origen.pk).cantidad_total, 6)

    def test_repeticion_conserva_instantanea_aunque_cambie_el_estado_o_el_stock(self):
        primera = self.registrar()
        Producto.objects.filter(pk=self.producto.pk).update(activo=False)
        Bodega.objects.filter(pk__in=(self.origen.pk, self.destino.pk)).update(activa=False)
        StockBodega.objects.filter(pk=self.stock_origen.pk).update(cantidad_total=15)
        repetida = self.registrar()
        self.assertEqual(repetida.status_code, 200, repetida.data)
        self.assertEqual(repetida.data['data']['stock'], primera.data['data']['stock'])
        self.assertEqual(StockBodega.objects.get(pk=self.stock_origen.pk).cantidad_total, 15)

    def test_valida_identificadores_cantidades_clave_y_campos_ajenos(self):
        for cambios in ({'cantidad': 0}, {'cantidad': -1}, {'cantidad': 1.5}, {'cantidad': True},
                        {'cantidad': 2147483648}, {'bodega_origen_id': 0}, {'producto_id': True},
                        {'solicitud_id': 'incorrecta'}, {'solicitud_id': None}, {'estado': 'PENDIENTE'},
                        {'bodega_destino_id': self.origen.pk}, {'usuario_id': self.admin.pk}):
            with self.subTest(cambios=cambios):
                self.assertEqual(self.registrar(**cambios).status_code, 400)
        payload = self.datos(); payload.pop('solicitud_id')
        self.assertEqual(self.client.post(ROOT, payload, format='json').status_code, 400)
        self.comprobar_sin_cambios()

    def test_bodegas_inexistentes_o_inactivas_no_aceptan_traslados(self):
        for campo in ('bodega_origen_id', 'bodega_destino_id'):
            self.assertEqual(self.registrar(**{campo: 999999}).status_code, 400)
        for bodega in (self.origen, self.destino):
            Bodega.objects.filter(pk=bodega.pk).update(activa=False)
            self.assertEqual(self.registrar().status_code, 400)
            Bodega.objects.filter(pk=bodega.pk).update(activa=True)
        self.comprobar_sin_cambios()

    def test_producto_inexistente_o_inactivo_no_se_transfiere(self):
        self.assertEqual(self.registrar(producto_id=999999).status_code, 404)
        Producto.objects.filter(pk=self.producto.pk).update(activo=False)
        self.assertEqual(self.registrar().status_code, 404)
        self.comprobar_sin_cambios()

    def test_stock_insuficiente_no_usa_cantidades_de_terceras_bodegas(self):
        r = self.registrar(cantidad=25)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['errores']['stock_origen'], 24)
        self.comprobar_sin_cambios()

    def test_sin_stock_en_origen_no_crea_filas_ni_traslado(self):
        self.stock_origen.delete()
        self.assertEqual(self.registrar().status_code, 409)
        self.assertFalse(StockBodega.objects.filter(producto=self.producto, bodega=self.origen).exists())
        self.assertFalse(Transferencia.objects.exists())

    def test_destino_sin_fila_recibe_un_stock_nuevo(self):
        self.stock_destino.delete()
        r = self.registrar()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['data']['stock']['destino_anterior'], 0)
        self.assertEqual(StockBodega.objects.get(producto=self.producto, bodega=self.destino).cantidad_total, 6)

    def test_limite_de_destino_no_produce_cambios_parciales(self):
        for cantidad in (2147483647,):
            StockBodega.objects.filter(pk=self.stock_destino.pk).update(cantidad_total=cantidad)
            self.assertEqual(self.registrar().status_code, 409)
            self.assertEqual(StockBodega.objects.get(pk=self.stock_origen.pk).cantidad_total, 24)
            self.assertEqual(StockBodega.objects.get(pk=self.stock_destino.pk).cantidad_total, cantidad)
            self.assertFalse(Transferencia.objects.exists())

    def test_transferencia_conserva_una_fila_en_ambos_extremos(self):
        self.assertEqual(self.registrar().status_code, 201)
        self.assertEqual(list(StockBodega.objects.filter(bodega__in=(self.origen, self.destino)).order_by('bodega_id').values_list('cantidad_total', flat=True)), [18, 12])
        self.assertEqual(StockBodega.objects.filter(bodega__in=(self.origen, self.destino)).count(), 2)
        self.assertEqual(StockBodega.objects.get(bodega=self.tercera).cantidad_total, 20)

    def test_fallo_en_el_segundo_stock_revierte_el_primero(self):
        original = QuerySet.update
        def actualizar(qs, **datos):
            if qs.model is StockBodega and qs.filter(bodega=self.destino).exists():
                return 0
            return original(qs, **datos)
        with patch.object(QuerySet, 'update', actualizar):
            self.assertEqual(self.registrar().status_code, 409)
        self.comprobar_sin_cambios()

    def test_fallo_de_auditoria_notificacion_o_sms_revierte_todo(self):
        for funcion in ('registrar_auditoria', 'notificar_administradores', 'evaluar_alerta_sms'):
            with self.subTest(funcion=funcion), patch('apps.productos.views_transferencias.' + funcion, side_effect=RuntimeError('fallo de prueba')):
                with self.assertLogs('django.request', level='ERROR'), self.assertRaises(RuntimeError):
                    self.registrar()
            self.comprobar_sin_cambios()

    def test_evaluacion_sms_recibe_ambas_bodegas_con_sus_cantidades_nuevas(self):
        valores = []
        def evaluar(producto, bodega):
            valores.append((producto.pk, bodega.pk, StockBodega.objects.get(producto=producto, bodega=bodega).cantidad_total))
        with patch('apps.productos.views_transferencias.evaluar_alerta_sms', side_effect=evaluar):
            self.assertEqual(self.registrar().status_code, 201)
        self.assertEqual(valores, [(self.producto.pk, self.origen.pk, 18), (self.producto.pk, self.destino.pk, 12)])

    def test_permiso_especifico_sin_exigir_permisos_de_mermas_o_entradas(self):
        self.assertFalse(self.usuario.tiene_permiso('registrar_merma'))
        self.assertFalse(self.usuario.tiene_permiso('registrar_entrada'))
        self.assertEqual(self.registrar().status_code, 201)
        self.usuario.rol.permisos.clear()
        self.assertEqual(self.registrar(solicitud_id=str(uuid.uuid4())).status_code, 403)
        for ruta in ('', 'opciones/', 'productos/', 'resolver/', '999/'):
            self.assertEqual(self.consultar(ruta).status_code, 403)

    def test_autenticacion_y_cuenta_activa_se_exigen_en_todas_las_rutas(self):
        rutas = ('', 'opciones/', 'productos/', 'resolver/', '999/')
        self.usuario.activo = False
        for ruta in rutas:
            self.assertEqual(self.consultar(ruta).status_code, 403)
        self.assertEqual(self.registrar().status_code, 403)
        self.client.force_authenticate(None)
        for ruta in rutas:
            self.assertEqual(self.consultar(ruta).status_code, 401)
        self.assertEqual(self.registrar().status_code, 401)

    def test_transferencias_inmutables_y_detalle_inexistente(self):
        r = self.registrar(); pk = r.data['data']['id']
        self.assertEqual(self.client.delete(ROOT + str(pk) + '/').status_code, 405)
        self.assertEqual(self.client.patch(ROOT + str(pk) + '/', {'cantidad': 1}, format='json').status_code, 405)
        self.assertEqual(self.consultar('999999/').status_code, 404)

    def test_detalle_guarda_cantidades_historicas_y_movimientos_reales(self):
        r = self.registrar(); pk = r.data['data']['id']
        StockBodega.objects.filter(pk=self.stock_origen.pk).update(cantidad_total=5)
        detalle = self.consultar(f'{pk}/')
        self.assertEqual(detalle.status_code, 200)
        self.assertEqual(detalle.data['data']['stock']['origen_posterior'], 18)
        self.assertEqual(detalle.data['data']['detalles'][0]['sku'], 'TR-001')
        self.assertEqual(set(detalle.data['data']['movimientos'].values()), set(Movimiento.objects.values_list('pk', flat=True)))

    def test_historial_anterior_con_varios_productos_no_inventa_stock(self):
        t = Transferencia.objects.create(bodega_origen=self.origen, bodega_destino=self.destino, usuario=self.usuario, estado='PENDIENTE')
        p = Producto.objects.create(sku='OTRO', nombre='Otro producto')
        DetalleTransferencia.objects.create(transferencia=t, producto=self.producto, cantidad=2)
        DetalleTransferencia.objects.create(transferencia=t, producto=p, cantidad=3)
        r = self.consultar(f'{t.pk}/')
        self.assertEqual(r.data['data']['cantidad_total'], 5)
        self.assertEqual(len(r.data['data']['detalles']), 2)
        self.assertIsNone(r.data['data']['stock'])
        self.assertEqual(self.consultar(search='producto').data['count'], 1)

    def test_historial_paginado_estable_con_filtros_bodegas_inactivas_y_pocos_selects(self):
        ahora = timezone.now()
        for i in range(55):
            t = Transferencia.objects.create(bodega_origen=self.origen, bodega_destino=self.destino, usuario=self.usuario, estado='COMPLETADA')
            Transferencia.objects.filter(pk=t.pk).update(fecha_creacion=ahora + timedelta(seconds=i))
            DetalleTransferencia.objects.create(transferencia=t, producto=self.producto, cantidad=i + 1)
        Bodega.objects.filter(pk=self.destino.pk).update(activa=False)
        ids = []
        for page, n in ((1, 25), (2, 25), (3, 5)):
            with CaptureQueriesContext(connection) as consultas:
                r = self.consultar(page=page, origen=self.origen.pk, destino=self.destino.pk, estado='COMPLETADA', search='TR-001')
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(r.data['count'], 55)
            self.assertEqual(len(r.data['results']), n)
            self.assertLessEqual(len(consultas), 5)
            ids.extend(t['id'] for t in r.data['results'])
            self.assertIn('no-store', r['Cache-Control'])
        self.assertEqual(len(set(ids)), 55)
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.assertEqual(len(self.consultar(page='last').data['results']), 5)
        self.assertEqual(self.consultar(origen=self.destino.pk).data['count'], 0)

    def test_valida_fechas_estado_y_pagina_del_historial(self):
        for params in ({'desde': 'incorrecta'}, {'desde': '2026-10-30', 'hasta': '2026-10-01'},
                       {'estado': 'OTRO'}, {'origen': -1}, {'search': 'x' * 201}):
            self.assertEqual(self.consultar(**params).status_code, 400)
        self.assertEqual(self.consultar(page=20).status_code, 404)

    def test_catalogo_tiene_stock_de_ambas_bodegas_y_excluye_sin_existencias(self):
        sin_stock = Producto.objects.create(sku='SIN-STOCK', nombre='Sin stock')
        StockBodega.objects.create(producto=sin_stock, bodega=self.destino, cantidad_total=100)
        r = self.consultar('productos/', origen=self.origen.pk, destino=self.destino.pk)
        self.assertEqual(r.data['count'], 1)
        p = r.data['results'][0]
        self.assertEqual((p['stock_origen'], p['stock_destino']), (24, 6))
        self.assertEqual((p['bodega_origen_id'], p['bodega_destino_id']), (self.origen.pk, self.destino.pk))
        self.assertEqual(self.consultar('productos/', origen=self.origen.pk, destino=self.destino.pk, search='SECUNDARIO').data['count'], 1)

    def test_catalogo_paginado_y_resolver_encuentra_un_producto_fuera_de_pagina(self):
        for i in range(55):
            p = Producto.objects.create(sku=f'PAG-{i:03d}', nombre=f'Producto {i:03d}')
            StockBodega.objects.create(producto=p, bodega=self.origen, cantidad_total=1)
        for page, n in ((1, 25), (2, 25), (3, 6)):
            r = self.consultar('productos/', origen=self.origen.pk, destino=self.destino.pk, page=page)
            self.assertEqual(r.data['count'], 56)
            self.assertEqual(len(r.data['results']), n)
        r = self.consultar('resolver/', origen=self.origen.pk, destino=self.destino.pk, codigo='PAG-054')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['data']['stock_origen'], 1)
        self.assertEqual(r.data['data']['stock_destino'], 0)

    def test_resuelve_sku_codigo_secundario_y_gtin_equivalente_sin_consulta_externa(self):
        for codigo in ('tr-001', 'COD/SECUNDARIO', '4006381333931', '04006381333931', 'https://id.gs1.org/01/04006381333931'):
            with self.subTest(codigo=codigo):
                r = self.consultar('resolver/', origen=self.origen.pk, destino=self.destino.pk, codigo=codigo)
                self.assertEqual(r.status_code, 200, r.data)
                self.assertEqual(r.data['data']['id'], self.producto.pk)
        self.assertEqual(self.consultar('resolver/', origen=self.origen.pk, destino=self.destino.pk, codigo='NO-EXISTE').status_code, 404)

    def test_validaciones_de_contexto_y_lecturas_sin_stock(self):
        for ruta in ('productos/', 'resolver/'):
            for params in ({}, {'origen': self.origen.pk, 'destino': self.origen.pk}, {'origen': 999999, 'destino': self.destino.pk}):
                self.assertEqual(self.consultar(ruta, codigo='TR-001', **params).status_code, 400)
        self.stock_origen.delete()
        r = self.consultar('resolver/', origen=self.origen.pk, destino=self.destino.pk, codigo='TR-001')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['data']['stock_origen'], 0)

    def test_opciones_distingue_bodegas_activas_e_historicas(self):
        Bodega.objects.filter(pk=self.destino.pk).update(activa=False)
        r = self.consultar('opciones/').data['data']
        self.assertEqual({b['id'] for b in r['bodegas']}, {self.origen.pk, self.tercera.pk})
        self.assertEqual({b['id'] for b in r['bodegas_historial']}, {self.origen.pk, self.destino.pk, self.tercera.pk})
        self.assertTrue(r['permisos']['registrar'])


@override_settings(SMS_ALERTAS_ACTIVAS=False)
class ConcurrenciaTransferenciasTests(TransactionTestCase):
    def preparar(self):
        u = usuario_transferencias()
        a = Bodega.objects.create(nombre='Bodega Central')
        b = Bodega.objects.create(nombre='Otra')
        p = Producto.objects.create(sku='CONC-TR', nombre='Producto concurrente')
        StockBodega.objects.create(producto=p, bodega=a, cantidad_total=10)
        return u, a, b, p

    def ejecutar(self, operaciones):
        barrera = Barrier(len(operaciones))
        def operar(item):
            usuario, ruta, payload = item
            close_old_connections()
            try:
                client = APIClient(); client.force_authenticate(Usuario.objects.get(pk=usuario.pk))
                barrera.wait(timeout=10)
                return client.post(ruta, payload, format='json').status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(operaciones)) as pool:
            return sorted(pool.map(operar, operaciones))

    @skipUnlessDBFeature('has_select_for_update')
    def test_misma_solicitud_simultanea_se_completa_una_sola_vez(self):
        u, a, b, p = self.preparar()
        payload = {'bodega_origen_id': a.pk, 'bodega_destino_id': b.pk, 'producto_id': p.pk, 'cantidad': 7, 'solicitud_id': str(uuid.uuid4())}
        self.assertEqual(self.ejecutar([(u, ROOT, payload), (u, ROOT, payload)]), [200, 201])
        self.assertEqual(StockBodega.objects.get(bodega=a).cantidad_total, 3)
        self.assertEqual(StockBodega.objects.get(bodega=b).cantidad_total, 7)
        self.assertEqual(Transferencia.objects.count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_dos_personas_no_pueden_transferir_mas_que_el_stock_disponible(self):
        u, a, b, p = self.preparar(); otro = usuario_transferencias('otra-concurrente@example.com')
        datos = {'bodega_origen_id': a.pk, 'bodega_destino_id': b.pk, 'producto_id': p.pk, 'cantidad': 7}
        self.assertEqual(self.ejecutar([(u, ROOT, {**datos, 'solicitud_id': str(uuid.uuid4())}), (otro, ROOT, {**datos, 'solicitud_id': str(uuid.uuid4())})]), [201, 409])
        self.assertEqual(StockBodega.objects.get(bodega=a).cantidad_total, 3)
        self.assertEqual(Transferencia.objects.count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_traslados_opuestos_bloquean_bodegas_en_el_mismo_orden(self):
        u, a, b, p = self.preparar(); otro = usuario_transferencias('opuesta@example.com')
        p2 = Producto.objects.create(sku='CONC-2', nombre='Otro concurrente')
        StockBodega.objects.create(producto=p2, bodega=b, cantidad_total=10)
        solicitudes = [(u, ROOT, {'bodega_origen_id': a.pk, 'bodega_destino_id': b.pk, 'producto_id': p.pk, 'cantidad': 3, 'solicitud_id': str(uuid.uuid4())}),
                       (otro, ROOT, {'bodega_origen_id': b.pk, 'bodega_destino_id': a.pk, 'producto_id': p2.pk, 'cantidad': 4, 'solicitud_id': str(uuid.uuid4())})]
        self.assertEqual(self.ejecutar(solicitudes), [201, 201])
        for producto in (p, p2):
            self.assertEqual(StockBodega.objects.filter(producto=producto).aggregate(n=Sum('cantidad_total'))['n'], 10)

    @skipUnlessDBFeature('has_select_for_update')
    def test_merma_y_transferencia_comparten_el_bloqueo_de_producto(self):
        u, a, b, p = self.preparar()
        permiso = Permiso.objects.create(codigo='registrar_merma', nombre='Registrar merma', modulo='movimientos'); u.rol.permisos.add(permiso)
        solicitudes = [(u, ROOT, {'bodega_origen_id': a.pk, 'bodega_destino_id': b.pk, 'producto_id': p.pk, 'cantidad': 7, 'solicitud_id': str(uuid.uuid4())}),
                       (u, '/api/v1/productos/mermas/', {'bodega_id': a.pk, 'producto_id': p.pk, 'cantidad': 7, 'motivo': 'DAÑO', 'observacion': 'Prueba concurrente.'})]
        estados = self.ejecutar(solicitudes)
        self.assertIn(estados, ([201, 409], [201, 400]))
        self.assertEqual(StockBodega.objects.get(bodega=a).cantidad_total, 3)
        self.assertEqual(Transferencia.objects.count() + Merma.objects.count(), 1)
