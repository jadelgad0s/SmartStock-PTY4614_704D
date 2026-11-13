# Base de datos de SmartStock

SmartStock utiliza PostgreSQL para registrar productos, bodegas, ubicaciones, existencias por bodega, movimientos de inventario, mermas, usuarios y registros de auditoría.

## Conexión en producción

La aplicación web se ejecuta en Render y se conecta a PostgreSQL en Neon. Django lee la variable de entorno `DATABASE_URL` y requiere SSL para la conexión. Guarda la URL de producción en la configuración privada de Render. Conserva el archivo `.env` con las credenciales locales fuera del repositorio. [Configuración de producción](../Aplicaci%C3%B3n/SmartStock/smartstock/config/settings/production.py)

## Modelo de datos

Consulta las tablas y sus relaciones principales en el [diagrama entidad-relación de SmartStock](../../Evidencias%20de%20documentaci%C3%B3n/Arquitectura/Modelo%20de%20Datos/Diagrama%20Entidad-Relaci%C3%B3n%20%28DER%29%20SmartStock.png).

Las migraciones de Django se versionan con el código de la aplicación y permiten recrear la estructura en PostgreSQL. [Inventario](../Aplicaci%C3%B3n/SmartStock/smartstock/apps/productos/migrations) · [Usuarios](../Aplicaci%C3%B3n/SmartStock/smartstock/apps/usuarios/migrations) · [Auditoría](../Aplicaci%C3%B3n/SmartStock/smartstock/apps/core/migrations)

## Recrear la estructura en una base local

1. Crea una base vacía en PostgreSQL local, por ejemplo `smartstock_pruebas`, y usa un rol con permisos para crear tablas en su esquema.
2. Abre la carpeta que contiene `manage.py` y activa un entorno virtual con Python 3.13.7. [Carpeta de la aplicación](../Aplicaci%C3%B3n/SmartStock/smartstock)
3. Copia `.env.example` como `.env`. Configura `DB_NAME` con el nombre de la base de prueba, `DB_HOST=127.0.0.1`, `DB_PORT=5432` y los valores locales de `DB_USER`, `DB_PASSWORD` y `SECRET_KEY`. [Plantilla de configuración](../Aplicaci%C3%B3n/SmartStock/smartstock/.env.example)
4. Instala las dependencias, aplica las migraciones y comprueba su estado.

   ```bash
   python -m pip install -r requirements-web.txt
   python manage.py migrate --settings=config.settings.development
   python manage.py showmigrations --settings=config.settings.development
   ```

Django marca las migraciones aplicadas con `[X]`.
