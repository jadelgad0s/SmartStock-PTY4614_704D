"""Gestión web de la cola sin llamadas reales ni saldo de Twilio."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Auditoria
from apps.usuarios.models import Rol, Usuario
from .alertas_sms import mensaje_sms
from .models import (Bodega, EnvioAlertaSMS, EstadoStockSMS, LimiteDiarioSMS,
                     Notificacion, Producto, StockBodega, StockMinimo)
from .test_alertas_sms import AJUSTES, CLIENTE

ROOT = '/api/v1/alertas-sms/'


def crear_aviso(bodega, codigo, **extra):
    producto = Producto.objects.create(sku=codigo, nombre='Producto ' + codigo)
    StockBodega.objects.create(producto=producto, bodega=bodega, cantidad_total=5)
    StockMinimo.objects.create(producto=producto, bodega=bodega, cantidad_minima=5)
    ciclo = EstadoStockSMS.objects.create(producto=producto, bodega=bodega, nivel_maximo=1)
    return EnvioAlertaSMS.objects.create(producto=producto, bodega=bodega, ciclo=ciclo.ciclo, nivel=1,
        sku=codigo, producto_nombre=producto.nombre, bodega_nombre=bodega.nombre, cantidad=5, minimo=5,
        destinatario=AJUSTES['SMS_ALERTAS_DESTINATARIOS'][0], mensaje=mensaje_sms(producto, bodega, 5, 5, 1), **extra)


@override_settings(**AJUSTES)
class GestionSMSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(email='gestion-sms@example.com')
        cls.bodega = Bodega.objects.create(nombre='Bodega Central')
        cls.otra = Bodega.objects.create(nombre='Bodega Norte', activa=False)

    def setUp(self):
        self.client = APIClient(); self.client.force_authenticate(self.admin)
        self.parche = patch(CLIENTE); self.proveedor = self.parche.start(); self.addCleanup(self.parche.stop)
        self.serial = 0
        def aceptar(**kwargs):
            self.serial += 1
            return SimpleNamespace(sid='SM' + f'{self.serial:032x}', status='queued', error_code=None)
        self.proveedor.return_value.messages.create.side_effect = aceptar

    def procesar(self, *envios):
        return self.client.post(ROOT + 'procesar-pendientes/', {'ids': [str(e.pk) for e in envios]}, format='json')

    def test_abrir_consultar_detalle_y_preparar_no_envian_ni_modifican_cola(self):
        e = crear_aviso(self.bodega, 'LECTURA')
        antes = list(EnvioAlertaSMS.objects.values())
        for ruta in ('acceso/', 'opciones/', 'estado/', 'historial/', f'historial/{e.pk}/', 'preparar/'):
            self.assertEqual(self.client.get(ROOT + ruta).status_code, 200, ruta)
        self.assertEqual(list(EnvioAlertaSMS.objects.values()), antes)
        self.assertEqual(LimiteDiarioSMS.objects.count(), 0)
        self.assertEqual(Auditoria.objects.count(), 0)
        self.proveedor.assert_not_called()

    def test_solo_administrador_activo_y_rol_activo_pueden_gestionar(self):
        e = crear_aviso(self.bodega, 'ACCESO')
        rol = Rol.objects.create(codigo='administrador', nombre='Administrador SMS')
        admin_rol = Usuario.objects.create_user(email='admin-rol-sms@example.com', rol=rol)
        self.client.force_authenticate(admin_rol)
        self.assertTrue(self.client.get(ROOT + 'acceso/').data['data']['ver'])
        for objeto, campo in ((admin_rol, 'activo'), (rol, 'activo')):
            setattr(objeto, campo, False); objeto.save(update_fields=[campo])
            self.assertFalse(self.client.get(ROOT + 'acceso/').data['data']['ver'])
            for ruta in ('opciones/', 'estado/', 'historial/', 'preparar/', f'historial/{e.pk}/'):
                self.assertEqual(self.client.get(ROOT + ruta).status_code, 403)
            self.assertEqual(self.procesar(e).status_code, 403)
            self.assertEqual(self.client.post(ROOT + f'historial/{e.pk}/cancelar/', {}, format='json').status_code, 403)
            setattr(objeto, campo, True); objeto.save(update_fields=[campo])
        self.client.force_authenticate(Usuario.objects.create_user(email='operador-sms@example.com'))
        self.assertEqual(self.client.get(ROOT + 'historial/').status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(ROOT + 'acceso/').status_code, 401)

    def test_telefonos_y_credenciales_no_se_exponen_en_ninguna_consulta(self):
        e = crear_aviso(self.bodega, 'PRIVACIDAD')
        for ruta in ('estado/', 'opciones/', 'historial/', 'preparar/', f'historial/{e.pk}/'):
            r = self.client.get(ROOT + ruta)
            self.assertEqual(r.status_code, 200)
            for secreto in (AJUSTES['TWILIO_AUTH_TOKEN'], AJUSTES['TWILIO_ACCOUNT_SID'], e.destinatario):
                self.assertNotIn(secreto, r.content.decode())
        d = self.client.get(ROOT + f'historial/{e.pk}/').data['data']
        self.assertEqual(d['destinatario'], '+569*****222')
        self.assertEqual(d['mensaje'], e.mensaje)
        self.assertIn('no-cache', self.client.get(ROOT + 'historial/')['Cache-Control'])

    def test_motivos_distinguen_espera_cuota_configuracion_y_resultado_incierto(self):
        e = crear_aviso(self.bodega, 'MOTIVOS', proximo_intento=timezone.now() + timedelta(minutes=1))
        d = self.client.get(ROOT + f'historial/{e.pk}/').data['data']
        self.assertFalse(d['procesable']); self.assertIn('Espera', d['motivo'])
        EnvioAlertaSMS.objects.filter(pk=e.pk).update(proximo_intento=None)
        LimiteDiarioSMS.objects.create(fecha=timezone.localdate(), intentos=20)
        self.assertIn('límite diario', self.client.get(ROOT + f'historial/{e.pk}/').data['data']['motivo'])
        with override_settings(SMS_ALERTAS_ACTIVAS=False):
            self.assertIn('pausados', self.client.get(ROOT + f'historial/{e.pk}/').data['data']['motivo'])
        with override_settings(TWILIO_AUTH_TOKEN=''):
            self.assertIn('incompleta', self.client.get(ROOT + f'historial/{e.pk}/').data['data']['motivo'])
        EnvioAlertaSMS.objects.filter(pk=e.pk).update(estado='INCIERTO')
        d = self.client.get(ROOT + f'historial/{e.pk}/').data['data']
        self.assertFalse(d['procesable']); self.assertFalse(d['cancelable'])

    def test_historial_busca_producto_bodega_error_y_filtra_antes_de_paginar(self):
        e = crear_aviso(self.bodega, 'BUSCAR', codigo_error='21660')
        crear_aviso(self.otra, 'OTRA', estado='ENTREGADO')
        for texto in ('BUSCAR', 'Producto BUSCAR', 'Central', '21660'):
            r = self.client.get(ROOT + 'historial/', {'search': texto, 'bodega': self.bodega.pk})
            self.assertEqual(r.data['count'], 1)
        self.assertEqual(self.client.get(ROOT + 'historial/', {'estado': 'ENTREGADO'}).data['count'], 1)
        self.assertEqual(self.client.get(ROOT + 'historial/', {'bodega': self.otra.pk}).data['results'][0]['sku'], 'OTRA')
        d = self.client.get(ROOT + 'historial/').data
        self.assertEqual(d['revisables'], 1); self.assertEqual(d['zona_horaria'], 'America/Santiago')
        self.assertIn(str(e.pk), [r['id'] for r in d['results']])

    def test_fechas_incluyen_el_dia_completo_y_rechazan_rangos_invalidos(self):
        e = crear_aviso(self.bodega, 'FECHA')
        fecha = timezone.make_aware(datetime(2026, 11, 2, 23, 59, 59))
        EnvioAlertaSMS.objects.filter(pk=e.pk).update(fecha_creacion=fecha)
        self.assertEqual(self.client.get(ROOT + 'historial/', {'desde': '2026-11-02', 'hasta': '2026-11-02'}).data['count'], 1)
        for filtros in ({'desde': '2026-11-03', 'hasta': '2026-11-02'}, {'desde': 'no'}, {'hasta': '9999-12-31'}, {'bodega': 0}):
            self.assertEqual(self.client.get(ROOT + 'historial/', filtros).status_code, 400)

    def test_previsualizacion_selecciona_como_maximo_tres_y_respeta_filtros_y_cuota(self):
        envios = [crear_aviso(self.bodega, f'LOTE-{i}') for i in range(5)]
        crear_aviso(self.otra, 'OTRO-LOTE')
        for i, e in enumerate(envios):
            EnvioAlertaSMS.objects.filter(pk=e.pk).update(fecha_creacion=timezone.now() - timedelta(minutes=10-i))
        d = self.client.get(ROOT + 'preparar/', {'search': 'LOTE-', 'bodega': self.bodega.pk}).data['data']
        self.assertEqual([e['id'] for e in d['envios']], [str(e.pk) for e in envios[:3]])
        LimiteDiarioSMS.objects.create(fecha=timezone.localdate(), intentos=19)
        self.assertEqual(len(self.client.get(ROOT + 'preparar/').data['data']['envios']), 1)
        self.assertEqual(self.client.get(ROOT + 'preparar/', {'estado': 'ENTREGADO'}).status_code, 400)
        self.proveedor.assert_not_called()

    def test_confirmacion_procesa_solo_los_ids_aprobados_aunque_aparezcan_otras_alertas(self):
        e = crear_aviso(self.bodega, 'ELEGIDO')
        ids = self.client.get(ROOT + 'preparar/').data['data']['envios']
        nuevo = crear_aviso(self.bodega, 'NUEVO')
        r = self.client.post(ROOT + 'procesar-pendientes/', {'ids': [ids[0]['id']]}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        e.refresh_from_db(); nuevo.refresh_from_db()
        self.assertEqual((e.estado, nuevo.estado), ('ACEPTADO', 'PENDIENTE'))
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, 1)
        self.assertEqual(r.data['data']['resultados'][0]['id'], str(e.pk))
        self.assertTrue(Auditoria.objects.filter(modelo='EnvioAlertaSMS').exists())

    def test_repetir_la_misma_confirmacion_no_procesa_otros_avisos_ni_duplica_envios(self):
        e = crear_aviso(self.bodega, 'IDEMPOTENTE'); otro = crear_aviso(self.bodega, 'SIN-CONFIRMAR')
        for _ in range(2): self.assertEqual(self.procesar(e).status_code, 200)
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, 1)
        self.assertEqual(LimiteDiarioSMS.objects.get().intentos, 1)
        otro.refresh_from_db(); self.assertEqual(otro.estado, 'PENDIENTE')

    def test_payload_invalido_rechaza_duplicados_mas_de_tres_y_campos_desconocidos(self):
        e = crear_aviso(self.bodega, 'INVALIDO')
        for datos in ({'ids': []}, {'ids': [str(e.pk)] * 2}, {'ids': [str(uuid.uuid4()) for _ in range(4)]}, {'ids': ['no']}, {'limite': 100}, {'ids': [str(e.pk)], 'forzar': True}):
            self.assertEqual(self.client.post(ROOT + 'procesar-pendientes/', datos, format='json').status_code, 400)
        self.assertEqual(self.client.post(ROOT + 'procesar-pendientes/', {'ids': [str(uuid.uuid4())]}, format='json').status_code, 404)
        self.proveedor.assert_not_called(); self.assertEqual(Auditoria.objects.count(), 0)

    def test_confirmar_no_fuerza_la_espera_los_intentos_ni_un_estado_conocido(self):
        for i, cambios in enumerate(({'proximo_intento': timezone.now() + timedelta(minutes=2)}, {'intentos': 3}, {'estado': 'INCIERTO'}, {'estado': 'ENVIANDO'}, {'estado': 'ENTREGADO'}, {'twilio_sid': 'SM' + '8' * 32})):
            e = crear_aviso(self.bodega, f'PROTEGIDO-{i}', **cambios)
            self.assertEqual(self.procesar(e).status_code, 200)
        self.proveedor.assert_not_called()

    def test_cuota_agotada_o_servicio_pausado_bloquean_el_procesamiento(self):
        e = crear_aviso(self.bodega, 'CUOTA')
        with override_settings(SMS_ALERTAS_ACTIVAS=False):
            self.assertEqual(self.procesar(e).status_code, 409)
            self.assertEqual(self.client.get(ROOT + 'preparar/').data['data']['envios'], [])
        LimiteDiarioSMS.objects.create(fecha=timezone.localdate(), intentos=20)
        self.assertEqual(self.procesar(e).status_code, 409)
        self.proveedor.assert_not_called()

    def test_recuperacion_de_stock_cancela_el_aviso_al_revisarlo(self):
        e = crear_aviso(self.bodega, 'RECUPERADO')
        StockBodega.objects.filter(producto=e.producto).update(cantidad_total=20)
        r = self.procesar(e); self.assertEqual(r.status_code, 200)
        e.refresh_from_db(); self.assertEqual(e.estado, 'CANCELADO'); self.proveedor.assert_not_called()

    def test_timeout_se_conserva_como_incierto_y_otra_confirmacion_no_lo_reenvia(self):
        e = crear_aviso(self.bodega, 'TIMEOUT')
        self.proveedor.return_value.messages.create.side_effect = TimeoutError('simulado')
        with patch('apps.productos.alertas_sms.logger'): r = self.procesar(e)
        self.assertEqual(r.status_code, 200); e.refresh_from_db(); self.assertEqual(e.estado, 'INCIERTO')
        self.assertEqual(self.procesar(e).status_code, 200)
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, 1)

    def test_cancelar_es_idempotente_conserva_ciclo_stock_e_historial(self):
        e = crear_aviso(self.bodega, 'CANCELAR'); ciclo = e.ciclo
        for _ in range(2): self.assertEqual(self.client.post(ROOT + f'historial/{e.pk}/cancelar/', {}, format='json').status_code, 200)
        e.refresh_from_db(); self.assertEqual(e.estado, 'CANCELADO')
        self.assertEqual(EstadoStockSMS.objects.get(producto=e.producto).ciclo, ciclo)
        self.assertEqual(StockBodega.objects.get(producto=e.producto).cantidad_total, 5)
        self.assertEqual(Auditoria.objects.count(), 1); self.assertEqual(Notificacion.objects.count(), 1)
        self.assertEqual(EnvioAlertaSMS.objects.count(), 1); self.proveedor.assert_not_called()

    def test_cancelar_no_permite_cambiar_estados_ni_avisos_que_ya_salieron(self):
        e = crear_aviso(self.bodega, 'NO-CANCELAR')
        self.assertEqual(self.client.post(ROOT + f'historial/{e.pk}/cancelar/', {'estado': 'ENTREGADO'}, format='json').status_code, 400)
        for estado in ('ENVIANDO', 'INCIERTO', 'ACEPTADO', 'ENVIADO', 'ENTREGADO', 'RECHAZADO'):
            EnvioAlertaSMS.objects.filter(pk=e.pk).update(estado=estado)
            self.assertEqual(self.client.post(ROOT + f'historial/{e.pk}/cancelar/', {}, format='json').status_code, 409)

    def test_fallo_de_auditoria_impide_consumir_saldo_y_revierte_cancelacion(self):
        e = crear_aviso(self.bodega, 'AUDITORIA')
        with patch('apps.productos.views_alertas_sms.registrar_auditoria', side_effect=RuntimeError('simulado')):
            with self.assertRaises(RuntimeError): self.procesar(e)
            with self.assertRaises(RuntimeError): self.client.post(ROOT + f'historial/{e.pk}/cancelar/', {}, format='json')
        self.proveedor.assert_not_called(); e.refresh_from_db(); self.assertEqual(e.estado, 'PENDIENTE')

    def test_pantalla_y_menu_estan_integrados_en_todos_los_modulos(self):
        self.client.force_login(self.admin)
        for ruta in ('/dashboard/', '/productos/', '/bodegas/', '/ubicaciones/', '/movimientos/', '/transferencias/', '/mermas/', '/auditoria/', '/usuarios/', '/reportes/', '/alertas-sms/'):
            r = self.client.get(ruta)
            self.assertEqual(r.status_code, 200, ruta); self.assertContains(r, 'id="menu-sms"')
        html = self.client.get('/alertas-sms/').content.decode()
        self.assertIn('js/sms_base.js', html); self.assertIn('js/alertas_sms.js', html)
        self.assertIn('href="/alertas-sms/" class="nav-link sidebar-item active"', html)
        self.assertNotIn('href="/bodegas/" class="nav-link sidebar-item active"', html)


@override_settings(**AJUSTES)
class ConcurrenciaGestionSMSTests(TransactionTestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_superuser(email='sms-concurrente-ui@example.com')
        self.bodega = Bodega.objects.create(nombre='Pruebas SMS')
        self.e = crear_aviso(self.bodega, 'CON-1')
        self.parche = patch(CLIENTE); self.proveedor = self.parche.start(); self.addCleanup(self.parche.stop)
        self.proveedor.return_value.messages.create.return_value = SimpleNamespace(sid='SM'+'9'*32, status='queued', error_code=None)

    def simultaneos(self, operacion):
        barrera = Barrier(2)
        def ejecutar(i):
            close_old_connections()
            try:
                c = APIClient(); c.force_authenticate(Usuario.objects.get(pk=self.usuario.pk)); barrera.wait(timeout=10)
                return operacion(c, i)
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: return list(pool.map(ejecutar, range(2)))

    @skipUnlessDBFeature('has_select_for_update')
    def test_dos_confirmaciones_simultaneas_del_mismo_aviso_no_duplican_sms(self):
        r = self.simultaneos(lambda c, _: c.post(ROOT+'procesar-pendientes/', {'ids':[str(self.e.pk)]}, format='json').status_code)
        self.assertEqual(r, [200, 200]); self.assertEqual(self.proveedor.return_value.messages.create.call_count, 1)
        self.assertEqual(LimiteDiarioSMS.objects.get().intentos, 1)

    @skipUnlessDBFeature('has_select_for_update')
    @override_settings(SMS_ALERTAS_LIMITE_DIARIO=1)
    def test_lotes_distintos_comparten_la_cuota_diaria(self):
        otro = crear_aviso(self.bodega, 'CON-2')
        r = self.simultaneos(lambda c, i: c.post(ROOT+'procesar-pendientes/', {'ids':[str((self.e, otro)[i].pk)]}, format='json').status_code)
        self.assertTrue(all(s in (200, 409) for s in r)); self.assertIn(200, r)
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, 1)
        self.assertEqual(LimiteDiarioSMS.objects.get().intentos, 1)
        self.assertEqual(EnvioAlertaSMS.objects.filter(estado='PENDIENTE').count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_cancelar_y_procesar_simultaneamente_respetan_la_reserva(self):
        def operacion(c, i):
            return c.post(ROOT+(f'historial/{self.e.pk}/cancelar/' if i else 'procesar-pendientes/'), {} if i else {'ids':[str(self.e.pk)]}, format='json').status_code
        r = self.simultaneos(operacion); self.assertEqual(r[0], 200); self.assertIn(r[1], (200, 409))
        self.e.refresh_from_db(); self.assertIn(self.e.estado, ('ACEPTADO', 'CANCELADO'))
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, int(self.e.estado=='ACEPTADO'))

    def test_api_abre_la_red_despues_de_confirmar_reserva_y_auditoria(self):
        def aceptar(**kwargs):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(EnvioAlertaSMS.objects.get(pk=self.e.pk).estado, 'ENVIANDO')
            self.assertTrue(Auditoria.objects.filter(modelo='EnvioAlertaSMS').exists())
            return SimpleNamespace(sid='SM'+'9'*32, status='queued', error_code=None)
        self.proveedor.return_value.messages.create.side_effect = aceptar
        c=APIClient(); c.force_authenticate(self.usuario)
        self.assertEqual(c.post(ROOT+'procesar-pendientes/', {'ids':[str(self.e.pk)]}, format='json').status_code, 200)
        self.assertEqual(self.proveedor.return_value.messages.create.call_count, 1)
