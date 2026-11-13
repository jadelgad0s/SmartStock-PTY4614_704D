# Autocompletar productos desde códigos

En **Catálogo → Nuevo producto → Completar desde un código**, escribe el
código y pulsa **Buscar datos** o Enter. Un lector USB puede escribirlo en
ese campo. **Escanear** usa la cámara del navegador y confirma dos lecturas.
La cámara requiere HTTPS o localhost y permiso del usuario.

1. Se busca primero un SKU o código asociado en SmartStock, incluyendo
   productos inactivos. Un resultado existente permite abrir su detalle.
2. Si el código comercial es válido, se consulta Open Food Facts para
   alimentos y bebidas. Los QR GS1 Digital Link sin comprimir que incluyen
   `/01/GTIN-DE-14-DIGITOS` se resuelven por su GTIN. También se reconocen
   QR internos con un SKU o `https://smartstockchile.cl/productos/?q=SKU`.
3. Se completan **los campos vacíos** de nombre y descripción. Marca y
   presentación disponibles se incluyen en la descripción. La imagen se
   muestra como referencia; se conserva el enlace de procedencia al guardar.
   **Usar nombre y descripción sugeridos** aplica explícitamente esos valores
   sobre los campos ya escritos.
4. Revisa la ficha, completa el SKU interno y el precio en CLP, y pulsa
   **Crear producto**. Consultar un código no crea productos, movimientos,
   existencias ni alertas SMS. El código se asocia al producto al guardar.

Si no hay ficha, el código no es compatible, la fuente está ocupada o no
responde, el formulario permite continuar manualmente. Open Food Facts no
garantiza cobertura ni información completa. Los productos de ferretería
requieren otra fuente o registro manual. Un QR que solo enlaza una página
arbitraria no proporciona por sí solo los datos del producto.

## API y despliegue

`GET /api/v1/productos/consultar-codigo/?codigo=3017620422003`

- Requiere JWT, usuario activo y permiso `crear_producto`.
- Respuesta estándar `{success, mensaje, data}`. Los estados son `existente`,
  `externo`, `no_compatible`, `no_encontrado`, `indisponible` y `limite`.
- `externo` incluye `sugerencia`, `fuente` y `ficha_externa_id`. El formulario
  envía este ID en el POST normal del producto para conservar la procedencia.
- Una coincidencia ambigua local devuelve 409. Los errores de entrada
  devuelven 400. Un alta importada repetida se rechaza incluso cuando dos
  lectores usan EAN-13 y GTIN-14 del mismo producto.
- Se admiten GTIN-8, UPC-A, EAN-13 y GTIN-14 con dígito verificador válido.
  Los códigos locales se buscan aunque no tengan formato GTIN.
- No requiere clave de Open Food Facts, nuevas dependencias ni cambios en
  `.env`. Ejecuta `python manage.py migrate` antes de arrancar el servidor.
  Render ya ejecuta las migraciones en su comando de construcción.

## Consulta externa y procedencia

La consulta usa la API v3.6, idioma español, país Chile y un `User-Agent` de
SmartStock. Solo se envía el identificador comercial; el JWT del usuario,
precio, SKU interno y existencias permanecen en SmartStock. Los enlaces de
QR nunca son destinos de peticiones del servidor. No se siguen redirecciones
HTTP del proveedor. Se limita la respuesta a 64 KiB y la espera a 4 segundos,
sin reintentos automáticos.

La caché se guarda en `fichas_producto_externas`, separada de las existencias:
24 horas para fichas encontradas y 15 minutos para códigos sin resultados.
`cupos_consulta_externa` reserva como máximo 12 llamadas por minuto en una
ventana móvil, compartida mediante bloqueos de PostgreSQL entre usuarios y
procesos. Esto deja margen respecto del límite publicado de 15 lecturas por
minuto/IP. Un HTTP 429 pausa consultas y respeta `Retry-After` en segundos
(mínimo 60, máximo 3600). Una lectura desde caché no consume este cupo.

El formulario y el detalle muestran **Open Food Facts**, enlace al producto
y licencia **ODbL**. La imagen, si existe, se carga desde el dominio de imágenes
de Open Food Facts sin enviar el referente de SmartStock; no se descarga al
disco de Render ni sustituye el campo `imagen` del producto. Las imágenes
tienen licencia CC BY-SA. Al redistribuir datos o imágenes se deben conservar
las atribuciones y cumplir sus licencias; no se publica automáticamente el
inventario privado ni se envían datos a la API de escritura de Open Food Facts.

Referencias oficiales:

- [Introducción y límites de la API](https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/)
- [Consulta de productos v3](https://openfoodfacts.github.io/documentation/docs/Product-Opener/v3/products/get-api-v3-product-code/)
- [Normalización de códigos](https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/ref-barcode-normalization/)
- [Licencias de los datos e imágenes](https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/tutorials/license-be-on-the-legal-side/)
- [GS1 Digital Link](https://ref.gs1.org/standards/digital-link/uri-syntax/)

## Verificación local

En Windows CMD, desde la carpeta que contiene `manage.py`, con el entorno
virtual activo y tu configuración habitual de desarrollo:

```bat
python manage.py migrate
python manage.py check
python manage.py test apps.productos.test_consulta_codigos
python manage.py runserver
```

Las pruebas sustituyen las peticiones externas y no envían SMS. Para probar
el formulario, usa primero un código de tu catálogo y después un código real
de alimento o bebida que todavía no tengas registrado. `3017620422003` sirve
como ejemplo de consulta; el contenido de una fuente externa puede cambiar.
Las pruebas de reservas y altas simultáneas requieren PostgreSQL y se omiten
cuando se utiliza SQLite.
