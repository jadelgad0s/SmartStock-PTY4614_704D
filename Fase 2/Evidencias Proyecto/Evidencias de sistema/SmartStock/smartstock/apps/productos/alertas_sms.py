"""Cola persistente de SMS. La red se utiliza después del commit de inventario."""
from datetime import timedelta
from functools import partial
import logging
import re
import unicodedata
from urllib.parse import urlsplit
import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Sum
from django.urls import reverse
from django.utils import timezone
from twilio.base.exceptions import TwilioRestException
from twilio.http.http_client import TwilioHttpClient
from twilio.rest import Client

from .models import Bodega, EnvioAlertaSMS, EstadoStockSMS, LimiteDiarioSMS, Producto, StockBodega, StockMinimo
from .stock import estado_stock

logger = logging.getLogger(__name__)
NIVELES = {'suficiente': 0, 'bajo': 1, 'agotado': 2}
ESTADOS_TWILIO = {
    'accepted': 'ACEPTADO', 'queued': 'ACEPTADO', 'sending': 'ACEPTADO',
    'sent': 'ENVIADO', 'delivered': 'ENTREGADO',
    'undelivered': 'NO_ENTREGADO', 'failed': 'RECHAZADO', 'canceled': 'CANCELADO',
}
PRIORIDAD = {'PENDIENTE': 0, 'ENVIANDO': 0, 'INCIERTO': 0, 'ACEPTADO': 1,
             'ENVIADO': 2, 'RECHAZADO': 3, 'NO_ENTREGADO': 3, 'CANCELADO': 3, 'ENTREGADO': 4}


def configuracion_sms():
    """No devuelve secretos. Los teléfonos solo se exponen enmascarados por la API."""
    destinatarios = list(dict.fromkeys(settings.SMS_ALERTAS_DESTINATARIOS))
    errores = []
    if not 1 <= len(destinatarios) <= 3 or any(not re.fullmatch(r'\+569[0-9]{8}', str(n)) for n in destinatarios):
        errores.append('Configura entre 1 y 3 móviles chilenos autorizados en SMS_ALERTAS_DESTINATARIOS (+569XXXXXXXX).')
    if not re.fullmatch(r'AC[0-9a-fA-F]{32}', settings.TWILIO_ACCOUNT_SID):
        errores.append('Configura TWILIO_ACCOUNT_SID.')
    if not settings.TWILIO_AUTH_TOKEN:
        errores.append('Configura TWILIO_AUTH_TOKEN.')
    if settings.TWILIO_MESSAGING_SERVICE_SID:
        if not re.fullmatch(r'MG[0-9a-fA-F]{32}', settings.TWILIO_MESSAGING_SERVICE_SID):
            errores.append('Revisa TWILIO_MESSAGING_SERVICE_SID.')
    elif not re.fullmatch(r'\+[1-9][0-9]{7,14}', settings.TWILIO_FROM_NUMBER):
        errores.append('Configura TWILIO_MESSAGING_SERVICE_SID o TWILIO_FROM_NUMBER con capacidad SMS.')
    try:
        url = urlsplit(settings.TWILIO_PUBLIC_BASE_URL)
    except ValueError:
        url = urlsplit('')
    if (url.scheme != 'https' or not url.netloc or url.username or url.password
            or url.path not in ('', '/') or url.query or url.fragment):
        errores.append('TWILIO_PUBLIC_BASE_URL debe ser el origen HTTPS público, sin rutas ni parámetros.')
    if not 1 <= settings.SMS_ALERTAS_LIMITE_DIARIO <= 1000:
        errores.append('SMS_ALERTAS_LIMITE_DIARIO debe estar entre 1 y 1000 intentos.')
    if not 1 <= settings.SMS_ALERTAS_TIMEOUT <= 5:
        errores.append('SMS_ALERTAS_TIMEOUT debe estar entre 1 y 5 segundos.')
    return {'activa': settings.SMS_ALERTAS_ACTIVAS, 'lista': not errores,
            'destinatarios': destinatarios, 'errores': errores}


def telefono_oculto(telefono):
    return '+569*****' + telefono[-3:]


def existencias_sms(producto_id, bodega_id):
    cantidad = StockBodega.objects.filter(producto_id=producto_id, bodega_id=bodega_id).aggregate(total=Sum('cantidad_total'))['total'] or 0
    minimo = StockMinimo.objects.filter(producto_id=producto_id, bodega_id=bodega_id).aggregate(total=Max('cantidad_minima'))['total'] or 0
    return cantidad, max(0, minimo)


def texto_ascii(texto):
    # Evitar Unicode y caracteres GSM extendidos: un SMS de hasta 160 septetos.
    texto = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    texto = re.sub(r'[\x00-\x1f\x7f]', ' ', texto)
    texto = re.sub(r'[\[\]\\^{}~|`]', '-', texto)
    return ' '.join(texto.split())


def mensaje_sms(producto, bodega, cantidad, minimo, nivel):
    titulo = f'SmartStock: {"stock bajo" if nivel == 1 else "agotado"}'
    nombre = texto_ascii(producto.nombre) or 'Producto'
    ubicacion = texto_ascii(bodega.nombre) or 'Bodega'
    unidades = f'Queda {cantidad} unidad' if cantidad == 1 else f'Quedan {cantidad} unidades'
    resumen = f'{unidades}. El minimo es {minimo}.'
    cierre = [f'SKU {texto_ascii(producto.sku)}', 'STOP para salir.']
    instruccion = f'Reponer {nombre} en {ubicacion}.'
    completo = '\n\n'.join([titulo, instruccion + '\n' + resumen, '\n'.join(cierre)])
    if len(completo) <= 160:
        return completo

    # Quitar las líneas en blanco antes de abreviar datos del producto.
    compacto = '\n'.join([titulo, instruccion, resumen, *cierre])
    if len(compacto) <= 160:
        return compacto

    # Con datos extensos, conservar identidad, ubicación y cantidades en una
    # ficha compacta. Los saltos de línea GSM básicos ocupan un septeto.
    resumen = f'Stock: {cantidad}. Minimo: {minimo}.'
    espacio = 160 - len('\n'.join([titulo, '', '', resumen, *cierre]))
    limite_bodega = min(len(ubicacion), max(espacio // 2, espacio - len(nombre)))
    limite_nombre = espacio - limite_bodega

    def acortar(texto, limite):
        if len(texto) <= limite:
            return texto
        return texto[:limite - 3].rstrip() + '...' if limite > 3 else texto[:limite]

    return '\n'.join([titulo, acortar(nombre, limite_nombre),
                      acortar(ubicacion, limite_bodega), resumen, *cierre])


def callback_url(envio_id):
    return settings.TWILIO_PUBLIC_BASE_URL.rstrip('/') + reverse('sms-twilio-estado', kwargs={'envio_id': envio_id})


@transaction.atomic
def evaluar_alerta_sms(producto, bodega):
    """Se llama dentro de la transacción que ya bloqueó el producto."""
    configuracion = configuracion_sms()
    destinatarios = configuracion['destinatarios']
    habilitada = (settings.SMS_ALERTAS_ACTIVAS and 1 <= len(destinatarios) <= 3
                  and all(re.fullmatch(r'\+569[0-9]{8}', str(n)) for n in destinatarios))
    if not producto.activo or not bodega.activa:
        return
    # Si se pausaron los SMS, seguir reconociendo recuperaciones de ciclos ya
    # existentes. No crear estado ni alertas nuevas mientras están desactivados.
    if not habilitada and not EstadoStockSMS.objects.filter(producto=producto, bodega=bodega).exists():
        return
    cantidad, minimo = existencias_sms(producto.pk, bodega.pk)
    nivel = NIVELES[estado_stock(cantidad, minimo)]
    estado, _ = EstadoStockSMS.objects.select_for_update().get_or_create(producto=producto, bodega=bodega)
    pendientes = EnvioAlertaSMS.objects.filter(producto=producto, bodega=bodega, estado='PENDIENTE')
    if nivel == 0:
        pendientes.update(estado='CANCELADO', detalle='El stock se recuperó o se desactivó el mínimo.', fecha_modificacion=timezone.now())
        if estado.nivel_maximo:
            estado.nivel_maximo = 0
            estado.ciclo = uuid.uuid4()
            estado.save(update_fields=['nivel_maximo', 'ciclo', 'fecha_modificacion'])
        return
    if not habilitada:
        return
    if nivel <= estado.nivel_maximo:
        return
    pendientes.update(estado='CANCELADO', detalle='Reemplazado por una alerta más crítica.', fecha_modificacion=timezone.now())
    estado.nivel_maximo = nivel
    estado.save(update_fields=['nivel_maximo', 'fecha_modificacion'])
    for telefono in destinatarios:
        envio = EnvioAlertaSMS.objects.create(
            producto=producto, bodega=bodega, ciclo=estado.ciclo, nivel=nivel,
            sku=producto.sku, producto_nombre=producto.nombre, bodega_nombre=bodega.nombre,
            cantidad=cantidad, minimo=minimo, destinatario=telefono,
            mensaje=mensaje_sms(producto, bodega, cantidad, minimo, nivel),
        )
        transaction.on_commit(partial(enviar_alerta_sms, envio.pk), robust=True)


@transaction.atomic
def cancelar_alertas_producto(producto):
    EnvioAlertaSMS.objects.filter(producto=producto, estado='PENDIENTE').update(
        estado='CANCELADO', detalle='Producto desactivado.', fecha_modificacion=timezone.now(),
    )
    for estado in EstadoStockSMS.objects.select_for_update().filter(producto=producto):
        estado.ciclo = uuid.uuid4()
        estado.nivel_maximo = 0
        estado.save(update_fields=['ciclo', 'nivel_maximo', 'fecha_modificacion'])


def reservar_intento(envio_id, configuracion):
    """Reservar cuota y reclamar la fila antes de abrir la conexión externa."""
    with transaction.atomic():
        limite, _ = LimiteDiarioSMS.objects.select_for_update().get_or_create(fecha=timezone.localdate())
        envio = EnvioAlertaSMS.objects.select_for_update().filter(pk=envio_id).first()
        ahora = timezone.now()
        if (envio is None or envio.estado != 'PENDIENTE' or envio.twilio_sid or envio.intentos >= 3
                or (envio.proximo_intento and envio.proximo_intento > ahora)):
            return None
        producto = Producto.objects.filter(pk=envio.producto_id, activo=True).first()
        bodega = Bodega.objects.filter(pk=envio.bodega_id, activa=True).first()
        estado = EstadoStockSMS.objects.filter(producto_id=envio.producto_id, bodega_id=envio.bodega_id).first()
        cantidad, minimo = existencias_sms(envio.producto_id, envio.bodega_id)
        vigente = (producto and bodega and estado and estado.ciclo == envio.ciclo
                   and NIVELES[estado_stock(cantidad, minimo)] == envio.nivel
                   and envio.destinatario in configuracion['destinatarios'])
        if not vigente:
            envio.estado = 'CANCELADO'
            envio.detalle = 'La alerta ya no corresponde al estado o al destinatario actual.'
            envio.save(update_fields=['estado', 'detalle', 'fecha_modificacion'])
            return None
        if limite.intentos >= settings.SMS_ALERTAS_LIMITE_DIARIO:
            return None
        limite.intentos += 1
        limite.save(update_fields=['intentos'])
        envio.estado = 'ENVIANDO'
        envio.intentos += 1
        envio.ultimo_intento = ahora
        envio.proximo_intento = None
        envio.cantidad, envio.minimo = cantidad, minimo
        envio.producto_nombre, envio.bodega_nombre, envio.sku = producto.nombre, bodega.nombre, producto.sku
        envio.mensaje = mensaje_sms(producto, bodega, cantidad, minimo, envio.nivel)
        envio.detalle = ''
        envio.save()
        return envio


def enviar_alerta_sms(envio_id):
    configuracion = configuracion_sms()
    if not configuracion['activa'] or not configuracion['lista']:
        return
    envio = reservar_intento(envio_id, configuracion)
    if envio is None:
        return
    http = None
    try:
        http = TwilioHttpClient(timeout=settings.SMS_ALERTAS_TIMEOUT, max_retries=0)
        cliente = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, http_client=http)
        remitente = ({'messaging_service_sid': settings.TWILIO_MESSAGING_SERVICE_SID}
                     if settings.TWILIO_MESSAGING_SERVICE_SID else {'from_': settings.TWILIO_FROM_NUMBER})
        respuesta = cliente.messages.create(
            to=envio.destinatario, body=envio.mensaje, status_callback=callback_url(envio.pk),
            validity_period=300, **remitente,
        )
        if not re.fullmatch(r'SM[0-9a-fA-F]{32}', str(respuesta.sid)):
            raise ValueError('Respuesta sin identificador SMS válido.')
        with transaction.atomic():
            actual = EnvioAlertaSMS.objects.select_for_update().get(pk=envio.pk)
            # Un callback firmado puede llegar antes que la respuesta REST.
            if actual.twilio_sid and actual.twilio_sid != respuesta.sid:
                return
            actual.twilio_sid = respuesta.sid
            destino = ESTADOS_TWILIO.get(respuesta.status, 'ACEPTADO')
            if PRIORIDAD[destino] > PRIORIDAD[actual.estado]:
                actual.estado = destino
            codigo = str(respuesta.error_code or '')
            if destino == actual.estado and re.fullmatch(r'[0-9]{1,12}', codigo):
                actual.codigo_error = codigo
            actual.save(update_fields=['twilio_sid', 'estado', 'codigo_error', 'fecha_modificacion'])
    except TwilioRestException as exc:
        codigo = str(exc.code or '')
        codigo = codigo if re.fullmatch(r'[0-9]{1,12}', codigo) else ''
        cambios = {'codigo_error': codigo, 'fecha_modificacion': timezone.now()}
        if exc.status == 429 and envio.intentos < 3:
            cambios.update(estado='PENDIENTE', proximo_intento=timezone.now() + timedelta(minutes=1),
                           detalle='Twilio limitó las solicitudes; se puede procesar después de un minuto.')
        elif 400 <= exc.status < 500:
            cambios.update(estado='RECHAZADO', detalle='Twilio rechazó la solicitud. Revisa el código en su consola.')
        else:
            cambios.update(estado='INCIERTO', detalle='Twilio no confirmó el resultado. No se reenvía automáticamente.')
        EnvioAlertaSMS.objects.filter(pk=envio.pk, estado='ENVIANDO').update(**cambios)
    except Exception as exc:
        # No registrar el contenido de excepciones: podría contener teléfonos o credenciales.
        logger.warning('SMS sin confirmación: envio=%s tipo=%s', envio.pk, type(exc).__name__)
        EnvioAlertaSMS.objects.filter(pk=envio.pk, estado='ENVIANDO').update(
            estado='INCIERTO', detalle='Resultado desconocido. Consulta Twilio antes de cualquier reenvío.',
            fecha_modificacion=timezone.now(),
        )
    finally:
        if http is not None and http.session is not None:
            http.session.close()


def procesar_pendientes_sms(limite=3, *, envio_ids=None):
    """Compatible con Render Free: no requiere Redis, Celery ni otro servicio."""
    # Un proceso interrumpido tampoco se reintenta: pudo alcanzar al proveedor.
    EnvioAlertaSMS.objects.filter(estado='ENVIANDO', ultimo_intento__lt=timezone.now() - timedelta(minutes=5)).update(
        estado='INCIERTO', detalle='Proceso interrumpido. Revisa la consola de Twilio.', fecha_modificacion=timezone.now(),
    )
    consulta = EnvioAlertaSMS.objects.filter(estado='PENDIENTE', intentos__lt=3).exclude(proximo_intento__gt=timezone.now())
    if envio_ids is not None:
        consulta = consulta.filter(pk__in=envio_ids)
    ids = list(consulta.order_by('fecha_creacion', 'id').values_list('pk', flat=True)[:limite])
    for envio_id in ids:
        enviar_alerta_sms(envio_id)
    return len(ids)
