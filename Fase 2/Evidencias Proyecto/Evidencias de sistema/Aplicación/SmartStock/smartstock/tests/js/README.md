# Pruebas de comportamiento de los módulos de SmartStock

Estas pruebas ejecutan `static/js/productos.js`, `static/js/movimientos.js`,
`static/js/mermas.js`, `static/js/auditoria.js`, `static/js/usuarios_api.js`, `static/js/dashboard.js`
`static/js/bodegas.js`, `static/js/transferencias.js` y el componente compartido
`static/js/notificaciones.js`, `static/js/login.js` y `static/js/acceso.js` con el DOM de las pantallas,
respuestas HTTP controladas y temporizadores de búsqueda deterministas. No
necesitan servidor Django, credenciales ni base de datos. Complementan las
pruebas de API ejecutadas con `python manage.py test`.

Reportes también ejecuta `static/js/reportes_base.js` y `static/js/reportes.js`.
Cubre permisos de consulta/exportación, filtros de cada informe, selección paginada
de productos del Kardex, fechas, paginación de resultados, respuestas atrasadas,
errores y reintentos, CSV completo sin el número de página, bloqueo de doble envío,
descargas invalidadas por cambios de filtros y renovación de JWT. Las pruebas de
API comprueban la conciliación de saldos con mermas y transferencias, stock
heredado, exportación completa, fechas locales y textos seguros.

En Acceso cubren validación antes del envío, bloqueo de solicitudes repetidas,
estados de procesamiento, errores de red y servidor, contenido HTTP mostrado
como texto y almacenamiento de sesión sin tokens parciales ante fallos. También
comprueban que las contraseñas con espacios conserven su valor, la visibilidad
accesible de contraseña, el POST nativo de recuperación y restablecimiento sin
deshabilitar sus campos, y la recuperación de controles al volver por historial.

Requieren Node.js 20 o posterior. Desde la raíz del proyecto:

```sh
npm --prefix tests/js install
npm --prefix tests/js test
```

En Catálogo cubren ambos paginadores, las seis opciones de orden, reinicio y persistencia
de búsqueda, respuestas atrasadas, recuperación de páginas eliminadas, catálogo
vacío y foco de teclado. También cubren filtros por estado/bodega/disponibilidad,
edición completa sin pérdida de descripción o códigos, códigos individuales con
tipo y principal, cámara con dos lecturas y retorno al formulario, errores por campo,
precios con decimales, confirmaciones con identidad, permisos y bloqueo de doble envío.
La configuración de mínimos por producto y bodega cubre carga actualizada, umbral
inclusivo, valor 0, errores, reintentos, permisos, respuestas atrasadas y retorno desde el detalle.
En Movimientos cubren búsqueda y filtros paginados,
lectura exacta de códigos, transición del registro manual, detalle, validación
de stock, confirmación y bloqueo de envíos duplicados, incluso durante el cierre
del modal tras guardar. La selección de bodega dentro del registro conserva los
datos, vuelve a consultar existencias y descarta respuestas anteriores; cubre
etiquetas de entrada/salida, reintentos, bodegas sin stock y confirmaciones
bloqueadas durante consultas o ante un contexto incorrecto.
En Mermas también cubren filtros, observaciones completas
en el detalle, paginación de productos, stock de Bodega Central, selección
invalidada por búsquedas nuevas y actualización del stock tras un rechazo.
En Auditoría cubren filtros, paginación, respuestas atrasadas, detalle seguro,
reintento de opciones, descarga autenticada de CSV y reporte completo de impresión.
También distinguen desactivaciones, reactivaciones y eliminaciones definitivas,
el código registrado de los eventos históricos y sus filtros en los reportes.
En Usuarios cubren paginación real, filtros, detalle, confirmación independiente de
contraseña, errores por campo, protección de cuentas, confirmaciones de acciones,
bloqueo de envíos repetidos y renovación compartida de JWT.
En Dashboard cubren indicadores por bodega, proporciones de productos, estados vacíos,
períodos, actualización manual y por visibilidad, respuestas atrasadas, gráficos sin
biblioteca, permisos, detalle, alertas paginadas y renovación compartida de JWT.
En Notificaciones cubren el aviso único en la campana, actualización durante consultas
pendientes, persistencia al navegar, lectura individual y total, avisos antiguos que
entran en la ventana de 20, errores y reintentos, enlaces seguros con filtros,
textos sin HTML, foco de teclado y sincronización entre pestañas.
En Transferencias cubren historial y catálogo paginados, bodegas activas e históricas,
permisos de consulta y registro, selección de origen y destino, stock de ambas bodegas,
cantidades válidas, lectura exacta de códigos fuera de la página, cámara y retorno al
formulario, errores y respuestas atrasadas. También comprueban la recuperación de
confirmaciones inciertas con la misma clave, incluso al recargar la pestaña, el bloqueo
de doble envío y la renovación de JWT sin cambiar el contenido de la transferencia.
JSDOM no calcula el diseño visual: para validar CSS,
revisar también el catálogo en un navegador con anchos de 320, 375, 576, 768 y
1366 px, usando productos con nombres largos y varias páginas.
