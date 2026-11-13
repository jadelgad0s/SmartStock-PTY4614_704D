# Reportes de inventario

La pantalla `/reportes/` se incorpora al menú de todas las pantallas. Permite
consultar 25 filas por página, exportar todos los resultados filtrados a CSV UTF-8
y preparar un documento para imprimir o guardar como PDF desde el navegador.

## Reportes disponibles

| Reporte | Selección y contenido |
| --- | --- |
| Existencias actuales | Una bodega, búsqueda por nombre/SKU y estado del producto. Incluye unidades, mínimo y clasificación del stock. |
| Stock crítico actual | Una bodega. Incluye productos agotados y aquellos con cantidad positiva menor o igual a su mínimo configurado. |
| Movimientos | Una o todas las bodegas, búsqueda, fechas y tipo de movimiento. Incluye entradas y salidas de transferencias. |
| Mermas y bajas | Una o todas las bodegas, búsqueda y fechas. Incluye motivo, observación completa y responsable. |
| Kardex por producto | Una bodega y un producto, incluidos productos inactivos. Orden cronológico, entradas, salidas y saldo después de cada registro. |

Existencias y stock crítico son consultas **actuales**. No aceptan fechas para
evitar presentar un stock actual como si fuera un conteo histórico. Un producto
sin registro de stock en la bodega tiene 0 unidades. Se suman filas heredadas de
stock duplicadas y se toma el mayor mínimo, igual que en el Catálogo.

Los filtros de fechas incluyen el día completo en `America/Santiago`, con límites
locales que contemplan los cambios de horario. Los documentos identifican los
filtros, fecha de generación, zona horaria, usuario, total y resúmenes del reporte.
Las bodegas inactivas se conservan disponibles para consultar su historial.

## Interpretación del Kardex

El Kardex reúne los detalles de movimientos y las mermas. Cada merma descuenta
unidades. Las transferencias ya generan una salida y una entrada en sus bodegas:
no se vuelve a sumar la tabla de transferencias. El saldo continúa entre páginas
y entre lotes del CSV.

El **saldo inicial calculado** se obtiene de las existencias actuales y los
registros disponibles desde el comienzo del período. Puede incluir stock cargado
antes del historial. No es una certificación de conteo físico histórico ni permite
recuperar movimientos que no se registraron. El saldo final de un período anterior
excluye las operaciones posteriores a ese período.

Los datos del producto, bodega y responsable usan sus nombres actuales. No se
agregan instantáneas históricas de nombres ni se modifica el esquema de datos.

## Permisos y exportación

- `ver_reportes`: consultar reportes, opciones y productos del Kardex.
- `exportar_reportes`, junto con `ver_reportes`: CSV e impresión/PDF.
- La cuenta y su rol deben estar activos. Los superusuarios activos tienen acceso.
- Se reutilizan los permisos que ya define `seed`; no se elevan permisos ni se
  ejecuta `seed --reset`. Los encargados con el permiso de consulta pueden leer,
  aunque no tengan permiso para exportar.

La API valida los permisos en cada solicitud. Los tokens viajan en la cabecera
`Authorization`, nunca en las URL de descarga. El CSV protege las celdas de texto
contra fórmulas y conserva numéricos los saldos negativos. El documento HTML
escapa los textos almacenados.

La vista y los archivos se preparan dentro de una transacción de lectura. En
PostgreSQL, las solicitudes sin una transacción exterior usan una instantánea
`REPEATABLE READ, READ ONLY`. El CSV se prepara por lotes en un archivo temporal
con memoria acotada; la descarga no mantiene una transacción ni cursor abiertos.
El archivo temporal se cierra al terminar la respuesta. No se guarda una copia
permanente ni se requiere disco persistente en Render.

La impresión tiene un máximo de 10.000 registros: si se supera, pide acotar los
filtros o descargar el CSV completo. No se recortan resultados silenciosamente.
Una exportación vuelve a consultar los datos al generarla y puede reflejar
operaciones nuevas posteriores a la vista. Sus propios metadatos indican cuándo
fue generada.

## API

Todas las rutas son GET autenticados y no almacenan respuestas en caché:

- `/api/v1/reportes/acceso/`: capacidades de consulta y exportación, sin inventario.
- `/api/v1/reportes/opciones/`: bodegas y permisos de la pantalla.
- `/api/v1/reportes/productos/?search=SKU&page=1`: productos paginados del Kardex.
- `/api/v1/reportes/consulta/`: vista paginada y metadatos.
- `/api/v1/reportes/exportar/`: CSV de todos los resultados filtrados.
- `/api/v1/reportes/imprimir/`: documento HTML de impresión.

Filtros comunes: `informe=existencias|critico|movimientos|mermas|kardex`, `bodega`,
`search`, `desde=AAAA-MM-DD`, `hasta=AAAA-MM-DD`. En stock: `productos=activos|todos|inactivos`.
En movimientos: `tipo=ENTRADA|SALIDA`. En Kardex: `producto` obligatorio y sin
búsqueda de texto de asientos, para conservar todos los eventos que forman el saldo.
`bodega` es obligatorio para stock y Kardex. `page` solo afecta a la consulta,
no al contenido de los archivos.

No se agregan tablas, migraciones ni dependencias. No se cambia la configuración
de SMS y consultar o exportar reportes no envía alertas ni modifica stock.
