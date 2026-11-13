"""Sugerencias autenticadas para el formulario de alta de productos."""
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.core.responses import error_response, success_response
from apps.usuarios.permissions import TienePermiso
from .consulta_codigos import consultar_open_food_facts, interpretar_codigo, procedencia, productos_registrados


class PuedeConsultarCodigo(TienePermiso):
    permiso_requerido = 'crear_producto'


class ConsultaCodigoSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=100)

    def validate_codigo(self, valor):
        if any(ord(c) < 32 or ord(c) == 127 for c in valor):
            raise serializers.ValidationError('El código contiene caracteres no válidos.')
        return valor


@never_cache
@api_view(['GET'])
@permission_classes([IsAuthenticated, PuedeConsultarCodigo])
def consultar_codigo(request):
    consulta = ConsultaCodigoSerializer(data=request.query_params)
    if not consulta.is_valid():
        return error_response(mensaje='Escribe o escanea un código válido.', errores=consulta.errors)
    codigo = consulta.validated_data['codigo']
    gtin, _ = interpretar_codigo(codigo)
    encontrados = productos_registrados(codigo)
    if len(encontrados) > 1:
        return error_response(mensaje='Este código coincide con más de un producto. Revisa sus SKU y códigos asociados.', status_code=409)
    if encontrados:
        p = encontrados[0]
        return success_response(data={'estado': 'existente', 'codigo': codigo, 'producto': {
            'id': p.pk, 'sku': p.sku, 'nombre': p.nombre, 'activo': p.activo,
        }}, mensaje='Este producto ya está registrado en SmartStock.')
    if not gtin:
        return success_response(data={'estado': 'no_compatible', 'codigo': codigo}, mensaje=(
            'No encontramos este código en SmartStock. La consulta externa admite EAN/UPC válidos y QR GS1 Digital Link. Puedes completar el producto manualmente.'
        ))
    resultado = consultar_open_food_facts(gtin)
    estado = resultado['estado']
    datos = {'estado': estado, 'codigo': codigo, 'gtin': gtin}
    mensajes = {
        'externo': 'Encontramos información. Revisa los datos antes de guardar.',
        'no_encontrado': 'No encontramos una ficha de este producto. Puedes completar los datos manualmente.',
        'indisponible': 'No pudimos consultar la fuente externa. Puedes reintentar o completar el producto manualmente.',
        'limite': 'La consulta externa está ocupada. Espera un momento o completa el producto manualmente.',
    }
    if estado == 'externo':
        ficha = resultado['ficha']
        datos.update({'ficha_externa_id': ficha.pk, 'sugerencia': ficha.datos, 'fuente': procedencia(ficha)})
    if 'reintentar_en' in resultado:
        datos['reintentar_en'] = resultado['reintentar_en']
    return success_response(data=datos, mensaje=mensajes[estado])
