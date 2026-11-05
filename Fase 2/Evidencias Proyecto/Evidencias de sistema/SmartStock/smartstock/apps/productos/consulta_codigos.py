"""Resolución local y sugerencias de Open Food Facts; nunca crea inventario."""
import json
import re
import socket
from datetime import timedelta
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.html import strip_tags

from .models import CodigoBarra, CupoConsultaExterna, FichaProductoExterna, Producto

PROVEEDOR = 'open_food_facts'
FUENTE = 'Open Food Facts'
LICENCIA_URL = 'https://opendatacommons.org/licenses/odbl/1-0/'
USER_AGENT = 'SmartStock/1.0 (https://smartstockchile.cl; contacto@smartstockchile.cl)'
MAX_RESPUESTA = 65536
# OFF permite 15 lecturas/min/IP. Se reserva margen y no se hacen reintentos.
CONSULTAS_POR_MINUTO = 12


def gtin_valido(codigo):
    if not re.fullmatch(r'(?:[0-9]{8}|[0-9]{12,14})', codigo or '') or not int(codigo):
        return False
    suma = sum(int(n) * (3 if i % 2 == 0 else 1)
               for i, n in enumerate(reversed(codigo[:-1])))
    return (10 - suma % 10) % 10 == int(codigo[-1])


def interpretar_codigo(codigo):
    """Un QR es dato, nunca una URL que el servidor deba visitar."""
    if gtin_valido(codigo):
        return codigo, None
    try:
        url = urlsplit(codigo)
        if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password:
            return None, None
        # QR internos: mismo buscador del catálogo, resuelto por SKU exacto.
        if url.hostname.lower() in ('smartstockchile.cl', 'www.smartstockchile.cl', 'localhost', '127.0.0.1') and url.path == '/productos/':
            params = parse_qs(url.query)
            valores = params.get('sku', params.get('q', []))
            if len(valores) == 1 and re.fullmatch(r'[A-Za-z0-9_-]{1,50}', valores[0]):
                return None, valores[0]
        # GS1 Digital Link sin comprimir: AI 01 seguido de GTIN-14.
        encontrados = re.findall(r'(?:^|/)01/([0-9]{14})(?=/|$)', unquote(url.path))
        if len(encontrados) == 1 and gtin_valido(encontrados[0]):
            return encontrados[0], None
    except (ValueError, UnicodeError):
        pass
    return None, None


def variantes_gtin(gtin):
    """EAN/UPC con ceros de relleno comparten la identidad GTIN-14."""
    if not gtin:
        return []
    canonico = gtin.zfill(14)
    return list(dict.fromkeys(canonico[-n:] for n in (14, 13, 12, 8)
                             if not canonico[:-n].strip('0') and gtin_valido(canonico[-n:])))


def productos_registrados(codigo):
    """Hasta dos coincidencias: una identidad o un conflicto que resolver."""
    gtin, sku_qr = interpretar_codigo(codigo)
    candidatos = list(dict.fromkeys([codigo, *variantes_gtin(gtin)]))
    criterio = Q(codigos_barra__codigo__in=candidatos) | Q(sku__iexact=codigo) | Q(sku__in=candidatos)
    if sku_qr:
        criterio |= Q(sku__iexact=sku_qr)
    if gtin:
        criterio |= Q(ficha_externa__gtin=gtin.zfill(14))
    encontrados = list(Producto.objects.filter(criterio).distinct().order_by('id')[:2])
    if gtin and len(encontrados) < 2:
        # QR GS1 registrados antes de existir el autocompletado. Se interpreta
        # el contenido guardado, sin visitar el enlace ni cambiar el registro.
        canonico = gtin.zfill(14)
        ids = {p.pk for p in encontrados}
        codigos_qr = CodigoBarra.objects.filter(tipo='QR', codigo__contains='/01/' + canonico).exclude(producto_id__in=ids).select_related('producto')
        for qr in codigos_qr.iterator(chunk_size=100):
            valor, _ = interpretar_codigo(qr.codigo)
            if valor and valor.zfill(14) == canonico and qr.producto_id not in ids:
                encontrados.append(qr.producto)
                ids.add(qr.producto_id)
                if len(encontrados) == 2:
                    break
    return encontrados


def procedencia(ficha):
    return {
        'nombre': FUENTE,
        'url': 'https://world.openfoodfacts.org/product/' + ficha.gtin,
        'licencia': 'ODbL', 'licencia_url': LICENCIA_URL,
        'imagen_url': ficha.datos.get('imagen_url', ''),
    }


def reservar_consulta():
    ahora = timezone.now()
    with transaction.atomic():
        CupoConsultaExterna.objects.get_or_create(proveedor=PROVEEDOR)
        cupo = CupoConsultaExterna.objects.select_for_update().get(pk=PROVEEDOR)
        if cupo.bloqueado_hasta and cupo.bloqueado_hasta > ahora:
            return max(1, int((cupo.bloqueado_hasta - ahora).total_seconds()) + 1)
        recientes = [t for t in cupo.intentos if t > ahora.timestamp() - 60]
        if len(recientes) >= CONSULTAS_POR_MINUTO:
            return max(1, int(min(recientes) + 60 - ahora.timestamp()) + 1)
        cupo.intentos = recientes + [ahora.timestamp()]
        cupo.bloqueado_hasta = None
        cupo.save(update_fields=['intentos', 'bloqueado_hasta'])
    return 0


def pausar_proveedor(segundos):
    CupoConsultaExterna.objects.filter(pk=PROVEEDOR).update(
        bloqueado_hasta=timezone.now() + timedelta(seconds=segundos),
    )


class SinRedirecciones(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def texto(valor, maximo):
    if not isinstance(valor, str):
        return ''
    return ' '.join(strip_tags(unescape(valor)).split())[:maximo]


def imagen_segura(valor):
    if not isinstance(valor, str) or len(valor) > 1000:
        return ''
    try:
        url = urlsplit(valor)
        if (url.scheme == 'https' and url.hostname == 'images.openfoodfacts.org'
                and not url.username and not url.password and url.port in (None, 443)
                and url.path.startswith('/images/products/')):
            return valor
    except ValueError:
        pass
    return ''


def imagen_producto(producto):
    seleccionadas = producto.get('selected_images')
    frente = seleccionadas.get('front') if isinstance(seleccionadas, dict) else None
    if isinstance(frente, dict):
        for tamano in ('small', 'display', 'thumb'):
            idiomas = frente.get(tamano)
            if not isinstance(idiomas, dict):
                continue
            for valor in (idiomas.get('es'), idiomas.get('en'), *idiomas.values()):
                imagen = imagen_segura(valor)
                if imagen:
                    return imagen
    return imagen_segura(producto.get('image_front_small_url')) or imagen_segura(producto.get('image_front_url'))


def datos_producto(producto):
    nombre = texto(producto.get('product_name_es') or producto.get('product_name'), 200)
    if not nombre:
        return {}
    marca = texto(producto.get('brands'), 150)
    presentacion = texto(producto.get('quantity'), 100)
    if presentacion and presentacion.casefold().replace(' ', '') not in nombre.casefold().replace(' ', ''):
        nombre = (nombre + ' ' + presentacion)[:200]
    descripcion = [texto(producto.get('generic_name_es') or producto.get('generic_name'), 1000)]
    if marca:
        descripcion.append('Marca: ' + marca)
    if presentacion:
        descripcion.append('Contenido: ' + presentacion)
    return {
        'nombre': nombre, 'descripcion': '\n'.join(t for t in descripcion if t),
        'marca': marca, 'presentacion': presentacion,
        'imagen_url': imagen_producto(producto),
    }


def consultar_open_food_facts(gtin):
    """Caché persistente, llamada acotada y sin enviar JWT/datos privados."""
    canonico = gtin.zfill(14)
    ficha = FichaProductoExterna.objects.filter(gtin=canonico, vence__gt=timezone.now()).first()
    if ficha:
        return {'estado': 'externo' if ficha.datos else 'no_encontrado', 'ficha': ficha, 'cache': True}
    espera = reservar_consulta()
    if espera:
        return {'estado': 'limite', 'reintentar_en': espera}
    fields = 'code,product_name,product_name_es,generic_name,generic_name_es,brands,quantity,selected_images,image_front_small_url,image_front_url'
    url = 'https://world.openfoodfacts.org/api/v3.6/product/' + gtin + '.json?' + urlencode({
        'fields': fields, 'lc': 'es', 'cc': 'cl',
    })
    req = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    datos = {}
    try:
        with build_opener(SinRedirecciones()).open(req, timeout=4) as respuesta:
            cuerpo = respuesta.read(MAX_RESPUESTA + 1)
            if len(cuerpo) > MAX_RESPUESTA:
                return {'estado': 'indisponible'}
            payload = json.loads(cuerpo)
        if not isinstance(payload, dict):
            return {'estado': 'indisponible'}
        producto = payload.get('product')
        if isinstance(producto, dict):
            codigo_respuesta = producto.get('code', payload.get('code'))
            if not isinstance(codigo_respuesta, str) or codigo_respuesta.zfill(14) != canonico:
                return {'estado': 'indisponible'}
            datos = datos_producto(producto)
        elif payload.get('status') not in (0, 'failure'):
            return {'estado': 'indisponible'}
    except HTTPError as error:
        if error.code == 429:
            try:
                segundos = min(3600, max(60, int(error.headers.get('Retry-After', '60'))))
            except (ValueError, TypeError):
                segundos = 60
            pausar_proveedor(segundos)
            return {'estado': 'limite', 'reintentar_en': segundos}
        if error.code != 404:
            return {'estado': 'indisponible'}
    except (URLError, OSError, socket.timeout, ValueError, UnicodeError):
        return {'estado': 'indisponible'}
    ficha, _ = FichaProductoExterna.objects.update_or_create(gtin=canonico, defaults={
        'datos': datos, 'vence': timezone.now() + (timedelta(days=1) if datos else timedelta(minutes=15)),
    })
    return {'estado': 'externo' if datos else 'no_encontrado', 'ficha': ficha, 'cache': False}
