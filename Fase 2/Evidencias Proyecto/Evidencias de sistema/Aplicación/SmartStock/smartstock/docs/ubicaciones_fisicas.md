# Ubicaciones físicas

Desde **Bodegas → Ubicaciones** se administra la estructura existente:
**bodega → pasillo → estantería → nivel → ubicación**. Cada producto del catálogo
también tiene un enlace **Ubicaciones**, que abre las referencias de ese producto
en la bodega consultada.

## Uso

En PC, **Ubicaciones** y **Editar** se mantienen visibles en cada bodega;
**Desactivar/Reactivar** se encuentra en **Más acciones**. En las tarjetas de
celular se conservan los tres accesos directos.

En Ubicaciones, los buscadores aparecen cuando hay más de diez opciones o una
búsqueda activa, y las flechas de paginación cuando hay más de una página. En
celular, cada paso se puede desplegar desde su encabezado; los demás muestran el
código seleccionado. Editar y Eliminar se agrupan en el menú **Administrar** de
cada paso. Los estados vacíos indican qué estructura falta crear y la asignación
queda atenuada hasta que haya una ubicación seleccionada.

1. Selecciona una bodega. Crea un pasillo, una estantería dentro de él, un nivel y
   finalmente una ubicación. Los selectores permiten buscar códigos y paginar de
   25 en 25, sin cargar toda la estructura.
2. Selecciona la ubicación de destino y pulsa **Asignar producto**. Busca por
   nombre, SKU o código de barras, elige el producto y confirma.
3. Consulta todas las referencias de la bodega o marca **Solo la ubicación
   seleccionada**. La búsqueda también encuentra códigos de pasillo, estantería,
   nivel y ubicación. El enlace desde el catálogo filtra por ese producto;
   **Ver todos los productos** quita ese filtro.
4. Un producto puede tener varias ubicaciones, incluso en diferentes bodegas.
   Repetir la misma asignación devuelve la referencia existente.
5. **Retirar referencia** quita la asociación. No elimina el producto. Los
   cambios se registran en Auditoría y en la campana.

Las asignaciones son **referencias para encontrar o guardar el producto**, no
una distribución de unidades. Pueden prepararse aunque el stock esté en cero.
Asignar o retirar una referencia no modifica `StockBodega`, no crea movimientos,
no cambia el Kardex ni genera SMS. Las entradas, salidas, transferencias y mermas
siguen controlando las cantidades por bodega.

Esta entrega usa los modelos y tablas existentes. No introduce migraciones,
tablas de sucursales ni permisos nuevos. Los campos heredados `cantidad` de
`ProductoUbicacion` y `capacidad_maxima` de `Ubicacion` se conservan y no se editan
desde esta interfaz. Si una referencia heredada tiene cantidad distinta de cero,
se muestra para revisión y se protege su eliminación; nunca se reinicia ni se
consolida automáticamente. Las referencias nuevas se crean con cantidad cero.

## Permisos y protecciones

- Lectura: `ver_bodega`. Escritura: también `editar_bodega`. Administradores y
  superusuarios tienen acceso. Los usuarios y roles inactivos no pueden operar.
- Las bodegas inactivas son de solo lectura. Los productos inactivos conservan
  sus referencias para consulta o retiro, pero no reciben asignaciones nuevas.
- Los códigos se normalizan a mayúsculas y no se repiten dentro del mismo padre
  por esta API. Puede existir, por ejemplo, una estantería E1 en cada pasillo.
- Al editar se cambia el código, no el padre ni la bodega de la estructura.
- Solo se elimina estructura vacía: un padre con hijos o una ubicación con
  productos asignados devuelve un conflicto. No hay borrados en cascada desde
  esta interfaz.
- Las escrituras bloquean la bodega; las asignaciones toman primero el producto,
  siguiendo el orden de las operaciones de inventario. Esto coordina altas,
  eliminaciones y asignaciones simultáneas realizadas por la API.
- Las operaciones y su auditoría son atómicas. No se corrigen ni se eliminan
  duplicados históricos de estructura automáticamente. La validación de códigos
  es de la API; no agrega restricciones nuevas a las tablas existentes.

## Prueba local en CMD

Con el entorno virtual activo y el servidor detenido con Ctrl+C:

```bat
git fetch origin
git switch mejora/ubicaciones-fisicas
git pull --ff-only
python -X utf8 manage.py check
python -X utf8 manage.py runserver
```

Se parte de `main` con el PR #31 de integridad de stock ya incorporado. Si esa
migración aún no está aplicada en tu instalación, sigue primero las instrucciones
de respaldo, diagnóstico y `migrate` de `docs/integridad_stock.md`.

Abre `/bodegas/` y pulsa **Ubicaciones** en una bodega. Prueba crear la estructura,
asignar un producto, repetir la asignación, buscarlo y retirar su referencia.
Comprueba que el catálogo y el Kardex conservan sus unidades. Repite con un
operador (consulta) y un encargado de bodega (edición). Prueba también el menú,
los formularios y el modo oscuro desde un celular.

```bat
python -X utf8 manage.py test apps.productos.test_ubicaciones --settings=config.settings.testing
```

Las pruebas de concurrencia requieren PostgreSQL. El workflow de GitHub ejecuta
la suite completa con PostgreSQL 16 aislado; `config.settings.testing` también
permite usar un PostgreSQL local de pruebas mediante `SS_TEST_POSTGRES=true` y
las variables `SS_TEST_DB_*` documentadas en `docs/integridad_stock.md`.
Las pruebas no usan la base de producción ni envían SMS reales. La configuración
de SMS de la aplicación se mantiene.
