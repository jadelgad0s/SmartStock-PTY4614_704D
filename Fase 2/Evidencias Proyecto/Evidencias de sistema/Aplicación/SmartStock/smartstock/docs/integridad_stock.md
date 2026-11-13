# Integridad del stock

La migración `productos.0007_integridad_stock` refuerza el inventario sin agregar
tablas ni cambiar las respuestas de la API.

| Tabla | Regla |
| --- | --- |
| `stock_bodega` | Una fila por producto/bodega. Cantidad entre 0 y 2.147.483.647. |
| `stock_minimo` | Una fila por producto/bodega. Mínimo entre 0 y 2.147.483.647. |
| `detalle_movimiento` | Cantidad entre 1 y 2.147.483.647. |
| `detalle_transferencia` | Cantidad entre 1 y 2.147.483.647. |
| `mermas` | Cantidad entre 1 y 2.147.483.647. |

Las reglas tienen validadores de modelo y restricciones reales de la base de
datos. Las restricciones también se aplican a `update()`, cargas y escrituras
fuera de los formularios. Stock 0 y mínimo 0 siguen siendo válidos.

## Datos existentes

Antes de crear las restricciones, la migración revisa **todas** las cantidades y
los totales por pareja. Si encuentra negativos, operaciones de 0 unidades o un
total de stock que exceda el rango, se detiene con las tablas y los IDs afectados.
No asigna cantidades nuevas ni recorta unidades para hacer pasar una restricción.

Si los datos son válidos, consolida cada pareja duplicada:

- Stock: conserva la suma de las unidades, por ejemplo 10 + 14 queda en 24.
- Mínimo: conserva el mayor configurado, por ejemplo 2 y 9 queda en 9.
- Conserva el ID menor y la fecha de modificación más reciente de las filas.
- Incluye productos y bodegas inactivos. No modifica otras parejas.

Esto conserva los valores que ya mostraban las consultas del catálogo. No crea
movimientos, auditorías, notificaciones ni SMS por la consolidación. Los
duplicados heredados se prueban con el esquema anterior mediante MigrationExecutor;
las pruebas de la aplicación usan desde ahora una fila por pareja.

La operación completa es atómica. En PostgreSQL bloquea brevemente las cinco
tablas de inventario para que una escritura no introduzca datos entre la revisión
y la creación de las restricciones. Si no obtiene el bloqueo en 10 segundos,
falla y revierte; debe repetirse cuando hayan terminado las operaciones activas.
No conviene ejecutarla mientras se registran entradas, salidas o transferencias.

Al revertir la migración se eliminan las restricciones, pero **no se recrean los
IDs ni las filas duplicadas**: los totales consolidados permanecen. Para recuperar
exactamente la disposición anterior de las filas se necesita el respaldo previo.

## Prueba local en CMD

Con el entorno virtual activo, detén `runserver` con Ctrl+C y entra en la rama.
Primero confirma que estás usando tu base **local**. El respaldo se guarda fuera
del repositorio para evitar subir datos de usuarios a GitHub.

```bat
git fetch origin
git switch mejora/integridad-stock
git pull --ff-only
set "SS_RESPALDO=%TEMP%\SmartStock_integridad_%RANDOM%.json"
python -X utf8 manage.py dumpdata --all --natural-foreign --natural-primary --indent 2 --output "%SS_RESPALDO%"
python -X utf8 manage.py revisar_integridad_stock
```

Confirma que el respaldo terminó correctamente. Si el diagnóstico encuentra
cantidades inválidas, conserva el archivo y revisa los registros señalados antes
de continuar; el comando es de solo lectura y no los corrige.

```bat
python -X utf8 manage.py migrate
python -X utf8 manage.py revisar_integridad_stock
python -X utf8 manage.py check
python -X utf8 manage.py runserver
```

Si una instalación está vacía, `migrate` crea las tablas y aplica la migración sin
necesidad de consolidar datos previos.

## Pruebas con PostgreSQL

`config.settings.testing` usa una SQLite aislada por defecto. Para comprobar los
bloqueos reales, selecciona explícitamente PostgreSQL **de pruebas**:

```bat
set "SS_TEST_POSTGRES=true"
set "SS_TEST_DB_NAME=smartstock_pruebas"
set "SS_TEST_DB_USER=postgres"
set "SS_TEST_DB_PASSWORD=CONTRASENA_DE_TU_POSTGRES_LOCAL"
set "SS_TEST_DB_HOST=127.0.0.1"
set "SS_TEST_DB_PORT=5432"
python -X utf8 manage.py test --settings=config.settings.testing --noinput
```

Crea primero una base vacía `smartstock_pruebas` en tu PostgreSQL local y usa un
usuario con permiso para crear la base temporal de Django. El runner crea y borra
`test_smartstock_pruebas`; no debe apuntarse a una base de producción. Estos
settings ignoran DATABASE_URL y las variables DB_* de la aplicación. Las alertas
reales se desactivan y el correo se captura en memoria durante las pruebas.

El workflow `.github/workflows/tests-postgres.yml` ejecuta la suite completa con
Python 3.13.7 y un PostgreSQL 16 aislado. Comprueba primero el motor para que los
casos de concurrencia no se omitan por ejecutar SQLite accidentalmente. Incluye
altas simultáneas del primer stock y del primer mínimo, inserciones duplicadas
fuera de la API, salidas contra salidas/mermas/transferencias, traslados opuestos,
repetición de una transferencia y coordinación del presupuesto SMS simulado.

## Neon y despliegue

Antes de aplicar a producción, ensaya el cambio con un respaldo o una rama aislada
de Neon y ejecuta el diagnóstico. Para migraciones y respaldos de Neon usa su
conexión **directa**, sin `-pooler` en el host. La conexión habitual de la web puede
seguir utilizando el pooler. La migración se ejecuta con los comandos de Django;
no es necesario crear restricciones manualmente desde la consola SQL.

La migración evita cambios parciales si un dato o bloqueo impide terminar. Una
vez aplicada, registra entradas, salidas, mermas y transferencias desde la web y
comprueba los saldos y el Kardex. La configuración de SMS de la aplicación se
mantiene.
