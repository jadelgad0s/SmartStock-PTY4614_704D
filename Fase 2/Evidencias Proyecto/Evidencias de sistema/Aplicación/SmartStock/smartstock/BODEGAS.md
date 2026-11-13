# Administración y operaciones por bodega

Esta entrega utiliza la tabla `bodegas` y sus relaciones existentes con stock,
movimientos, mermas y mínimos. No añade tablas ni columnas ni requiere cambiar
el modelo de datos documentado del proyecto.

## Uso

En **Bodegas** se pueden consultar, crear y editar bodegas con nombre y dirección
opcional, y desactivarlas o reactivarlas según los permisos del usuario.
El listado tiene búsqueda por nombre o dirección, filtro de estado y páginas de
25 registros. En celular se presenta mediante tarjetas.

Las bodegas actuales se muestran directamente. No es necesario asignarlas a
otra entidad ni volver a ingresar sus productos o cantidades.

En **Movimientos**, escanear o buscar el producto y elegir dentro de **Registrar
movimiento** la **Bodega de recepción** para una entrada o la **Bodega de salida**
para una salida. La selección superior es una preselección para agilizar lecturas
seguidas. Cambiar la bodega dentro del formulario conserva producto, tipo,
cantidad y observación, consulta sus existencias y actualiza la confirmación.
Mientras consulta o si falla la lectura, no permite guardar con stock anterior;
se puede reintentar la consulta. La última bodega elegida queda preseleccionada
para el siguiente registro.

Una entrada incorpora unidades directamente en la bodega elegida y una salida
las descuenta de ella. Para mover existencias que ya están registradas desde
una bodega a otra, usar **Transferencias**: descuenta origen y suma destino en
una sola operación, conservando el total del inventario.

En **Mermas**, elegirla dentro del formulario; cambiarla vuelve a consultar los
productos y descarta la selección anterior para evitar usar cantidades de otra
bodega.

Ambos historiales permiten filtrar por bodega, incluidas las inactivas para
consultar operaciones anteriores. El catálogo y el Dashboard siguen usando el
mismo conjunto de bodegas activas.

## Permisos y protección del inventario

- Administración y superusuarios administran bodegas. Los permisos existentes
  `crear_bodega`, `editar_bodega` y `eliminar_bodega` también conceden cada acción.
- Se conservan los permisos para registrar entradas, salidas y mermas.
- Una bodega con existencias, unidades en ubicaciones o transferencias pendientes
  no se puede desactivar. La desactivación conserva sus datos e historial.
- Una bodega inactiva no acepta nuevas operaciones ni cambios de mínimo.
- Bodega Central conserva su nombre como bodega predeterminada para los clientes
  anteriores que todavía no envían una selección explícita.
- Los cambios generan auditoría y avisos en la campana. La evaluación de SMS se
  realiza para el producto y la bodega operada, con la configuración actual de
  envíos.

## API

| Operación | Ruta | Datos |
| --- | --- | --- |
| Listar / crear | `GET/POST /api/v1/bodegas/` | Alta: `nombre` y `direccion` opcional |
| Consultar / editar / desactivar | `GET/PATCH/DELETE /api/v1/bodegas/{id}/` | DELETE desactiva y conserva el registro |
| Reactivar | `POST /api/v1/bodegas/{id}/activar/` | Sin cuerpo |
| Opciones y permisos | `GET /api/v1/bodegas/opciones/` | Bodegas activas, históricas y permisos |
| Consultar stock para movimiento | `GET /api/v1/productos/resolver-movimiento/?codigo=SKU&bodega=ID` | Existencias de la bodega indicada |
| Productos para merma | `GET /api/v1/productos/mermas/productos/?bodega=ID` | Catálogo paginado con stock de esa bodega |
| Registrar movimiento o merma | Rutas de registro actuales | Añadir `bodega_id` al JSON |
| Filtrar historiales | Rutas actuales de movimientos y mermas/historial | Añadir `bodega=ID` a la consulta |

El listado de bodegas acepta `search`, `activa=true/false` y `page`. Sin filtro de
estado muestra activas e inactivas. La web envía siempre la bodega expresamente;
los clientes anteriores sin selección siguen usando Bodega Central. Un ID
explícito inexistente o inactivo se rechaza sin utilizar otra bodega.

Las operaciones bloquean producto, bodega y stock dentro de una transacción y
vuelven a comprobar el estado de la bodega antes de escribir. El historial,
auditoría y descuento se confirman juntos. Si existen filas de stock duplicadas
heredadas, se suman y una operación consolida únicamente la pareja
producto/bodega que modifica, conservando su total.

## Prueba local

Con la rama del PR #27 seleccionada y el entorno virtual activo:

```bat
git pull --ff-only
set "DJANGO_SETTINGS_MODULE=config.settings.development"
python manage.py migrate
python manage.py runserver
```

Abrir `http://127.0.0.1:8000/bodegas/`. Esta entrega no incorpora migraciones
nuevas respecto a `main`; `migrate` solo aplica las pendientes del proyecto.

En una base de prueba, dejar un producto con 24 unidades en Central y 10 en una
segunda bodega. Registrar una salida de 3 y una merma de 1 en la segunda:
Central debe conservar 24 y la segunda quedar en 6. Comprobar ambos historiales
filtrados y que se rechace desactivar una bodega con existencias.

```bat
python manage.py test apps.productos.test_bodegas apps.productos.test_movimientos apps.productos.test_mermas apps.productos.test_mermas_historial
npm --prefix tests/js ci
npm --prefix tests/js test
```

Las pruebas de concurrencia que necesitan bloqueo de filas requieren PostgreSQL;
SQLite las omite. Las transferencias entre las bodegas actuales se describen en
[TRANSFERENCIAS.md](TRANSFERENCIAS.md). Los reportes/Kardex siguen como siguiente
entrega del plan.
