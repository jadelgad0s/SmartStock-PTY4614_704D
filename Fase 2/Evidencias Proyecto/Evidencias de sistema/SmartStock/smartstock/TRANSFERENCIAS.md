# Transferencias entre bodegas

En **Operaciones → Transferencias** se trasladan unidades de un producto entre
dos bodegas activas. El traslado se completa al confirmar: descuenta el origen
y suma el destino en una sola transacción. No hay una etapa de tránsito físico.

Para recibir mercadería nueva, usar **Movimientos → Entrada** y seleccionar la
**Bodega de recepción** dentro del registro. Para retirar unidades, usar
**Movimientos → Salida** y elegir la **Bodega de salida**. Transferencias se usa
cuando las unidades existentes pasan de una bodega a otra.

## Uso

1. Pulsar **Nueva transferencia** y seleccionar origen y destino diferentes.
2. Buscar un producto con existencias en origen o escribir/escanear su SKU,
   código de barras o QR ya registrado. Se puede usar teclado, lector físico
   o cámara. La búsqueda exacta encuentra productos fuera de la página actual.
3. Indicar una cantidad entera positiva. La pantalla muestra el stock de ambas
   bodegas antes y después del traslado.
4. Confirmar y revisar el aviso de la campana, el historial y el detalle.

Ejemplo: trasladar 6 unidades desde Central, que tiene 24, hacia Norte, que tiene
6. Central queda con **18**, Norte con **12** y el total se conserva en **30**.
Si no existe una fila de stock en destino, se crea con las unidades recibidas.
Los mínimos de stock de cada bodega conservan su configuración.

El historial permite buscar por producto/SKU y filtrar por origen, destino,
estado y fechas. Usa páginas de 25 registros y tarjetas en celular. Las bodegas
inactivas siguen disponibles como filtros para consultar el pasado.

Cada nueva transferencia incluye un producto. Los registros anteriores con
varios productos se muestran completos en el detalle. Las transferencias
completadas no se editan ni eliminan desde esta API; para devolver unidades se
registra un traslado nuevo en sentido contrario. Los registros anteriores en
estado pendiente son de consulta y no se completan desde este formulario.

## Permisos y registros

- Una cuenta activa autenticada puede consultar el historial y el detalle.
- Registrar exige el permiso existente `registrar_transferencia`; el seed lo
  asigna a administrador y encargado de bodega. El superusuario también puede
  registrar. El operador no lo recibe por defecto.
- Cada traslado crea una transferencia, su detalle, una salida y una entrada
  en el historial de Movimientos, con una referencia a la transferencia. Estas
  entradas/salidas también aparecen en los indicadores de su bodega.
- La auditoría registra una creación de `Transferencia`. La campana avisa a
  los administradores activos y a quien realizó la operación.
- Se evalúa la alerta SMS de ambas bodegas: la salida puede generar una alerta
  y la entrada puede recuperar stock y cancelar una alerta pendiente. Se usa
  la configuración de SMS existente, sin cambiar su activación ni sus límites.

## Confirmaciones y consistencia

El servidor vuelve a comprobar permisos, producto y bodegas activos, stock
suficiente y límites de cantidades. Bloquea usuario, producto, ambas bodegas
en orden de ID y sus filas de stock. Movimientos, stock, auditoría, campana e
historial se confirman juntos; una excepción revierte todo. Los envíos externos
de SMS se programan para después del commit.

Los duplicados de stock heredados se suman y se consolidan únicamente para las
dos parejas producto/bodega afectadas por una transferencia válida.

Cada confirmación lleva un UUID `solicitud_id`. Si se pierde la respuesta, la
pantalla conserva esa solicitud en la pestaña y ofrece **Verificar transferencia**.
El servidor devuelve el resultado anterior cuando esa cuenta repite la misma
clave y los mismos datos. Si el contenido cambia con una clave ya utilizada,
responde 409. Una transferencia distinta necesita un UUID nuevo.

La recuperación funciona también después de recargar esa pestaña. Si se cierra
la pestaña definitivamente o se borra el almacenamiento antes de verificar,
consultar el historial antes de iniciar otro traslado. Los clientes de la API
deben guardar y reutilizar el mismo UUID cuando el resultado sea incierto.

## API

Todas las rutas requieren `Authorization: Bearer TOKEN`.

| Método | Ruta bajo `/api/v1/productos/transferencias/` | Uso |
| --- | --- | --- |
| GET | raíz | Historial con `search`, `origen`, `destino`, `estado`, `desde`, `hasta`, `page` |
| POST | raíz | Confirmar el traslado |
| GET | `opciones/` | Bodegas activas, históricas y permisos |
| GET | `productos/?origen=1&destino=2` | Productos activos con stock positivo en origen; acepta `search` y `page` |
| GET | `resolver/?origen=1&destino=2&codigo=FER-001` | Producto registrado y stock en ambas bodegas |
| GET | `{id}/` | Detalle, cantidades históricas y movimientos asociados |

Ejemplo de cuerpo POST; reemplazar IDs y UUID para una operación nueva:

```json
{
  "bodega_origen_id": 1,
  "bodega_destino_id": 2,
  "producto_id": 10,
  "cantidad": 6,
  "solicitud_id": "b049821c-8e7b-4c17-a41c-9a3d88a0e140"
}
```

La primera confirmación devuelve 201; recuperar una ya registrada devuelve 200
con el mismo ID. Un conflicto de existencias devuelve 409 con el stock actual
en `errores.stock_origen` y `errores.stock_destino`. Las cantidades se limitan a
2.147.483.647 unidades, incluyendo los saldos resultantes.

## Tablas existentes

No se agregan tablas, columnas ni migraciones. Se utilizan `Transferencia`,
`DetalleTransferencia`, `StockBodega`, `Movimiento`, `DetalleMovimiento`,
`HistorialMovimientos`, `Auditoria` y `Notificacion`, además del servicio SMS.

La instantánea y la clave de confirmación se guardan en un registro existente
de `HistorialMovimientos`, con `tipo_registro=TRANSFERENCIA` y
`registro_id=ID_TRANSFERENCIA`. `descripcion` contiene JSON de versión 1:

```json
{
  "solicitud_id": "UUID",
  "version": 1,
  "stock": {"origen_anterior": 24, "origen_posterior": 18, "destino_anterior": 6, "destino_posterior": 12},
  "movimientos": {"salida": 101, "entrada": 102}
}
```

La clave se escribe al principio del JSON, en formato compacto; no reordenar
este contenido al editarlo por otras herramientas. La recuperación identifica
esa clave en el historial y comprueba la cuenta propietaria y los datos de la
transferencia. Los tipos de movimiento creados son `TRANSFERENCIA_SALIDA` y
`TRANSFERENCIA_ENTRADA`; el signo de su operación permite usar los filtros y
totales existentes. No modificar ni borrar sus registros de manera aislada.

## Prueba local en CMD

Con los cambios locales guardados y el entorno virtual activo, desde la carpeta
que contiene `manage.py`:

```bat
git fetch origin
git switch mejora/transferencias-bodegas
git pull --ff-only
set "DJANGO_SETTINGS_MODULE=config.settings.development"
python -X utf8 manage.py migrate
python -X utf8 manage.py runserver
```

Abrir `http://127.0.0.1:8000/transferencias/`. Tener dos bodegas activas y una
cuenta con el permiso indicado. Probar primero el ejemplo 24/6 → 18/12, revisar
ambos historiales de Movimientos y comprobar que una cantidad superior al stock
se rechace sin modificar ninguna bodega. `migrate` aplica solo las migraciones
pendientes del proyecto; esta entrega no introduce otras.

Pruebas automatizadas sobre una base de pruebas:

```bat
python -X utf8 manage.py test apps.productos.test_transferencias apps.productos.test_bodegas apps.productos.test_movimientos apps.core.test_pantallas_integradas
npm --prefix tests/js ci
npm --prefix tests/js test
```

Las pruebas de transferencia sustituyen la configuración SMS y no realizan
envíos reales. Las de concurrencia requieren PostgreSQL con bloqueos de fila;
SQLite las omite. Incluyen solicitudes simultáneas repetidas, salidas que
compiten por el mismo stock, traslados en sentidos opuestos y una merma
concurrente. La revisión visual se realiza también en navegador; JSDOM no
calcula las dimensiones CSS ni prueba una cámara física.
