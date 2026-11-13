# Integración del avance de otro integrante de SmartStock

**Fuente:** ZIP `SmartStock_20261019_2108.zip` compartido por el equipo.  
**Base:** `main` de SmartStock (`e5dec23` al crear la rama).
**Estado:** Rama de revisión; **NO DESPLEGAR** sin pruebas locales y validación de permisos.

## Integrado de forma selectiva

- **Dashboard:** se eliminaron valores ficticios/filas precargadas; los KPI muestran un placeholder hasta la respuesta real. Buscador por SKU, nombre o código que redirige al catálogo con `?q=`.
- **Catálogo:** se mantienen todos los módulos responsive y se añaden campos para asociar uno o varios códigos de barras a productos. La actualización comprueba que sean únicos por producto y que no pertenezcan a otro producto; la escritura usa `transaction.atomic`. La edición no permite sobrescribir códigos si no se pudieron cargar.
- **Cámara:** scanner `html5-qrcode` activado solo por acción de usuario, con dos lecturas consecutivas iguales, limpieza al cerrar y alternativa manual en escritorio/celular (HTTPS requerido).
- **Movimientos:** admite códigos de barras y SKU desde el catálogo y la API existente, incluso si el producto no está en la primera página del listado.
- **Notificaciones:** modelo + API por usuario (lectura, marcar una o todas) y avisos después de movimientos y mermas. Nuevo icono funcional sin exponer datos por `innerHTML` de proveedores; sin pedir permisos invasivos del navegador automáticamente.
- **Migraciones:** `0004_notificacion` depende de `0003_merma_observacion`, ya aplicada a producción. No se importa la conflictiva `0003_notificacion.py` del ZIP.

## Conservado de nuestra versión

- Mermas reales, auditoría, roles, permisos, seguridad JWT, recuperación de contraseña HTML y Resend.
- Interfaz responsive en celular y ajustes de modales, más favicon y logo.
- Configuración del despliegue y conexión a Neon sin cambios.

## Pendiente de decisión (no integrado)

El ZIP añade **eliminación permanente de productos y usuarios**. No se ha copiado por seguridad: incluso si un registro está sin stock, puede estar vinculado con auditoría, mermas, sesiones, permisos y otros registros históricos. Se mantiene la **desactivación reversible** que ya existe en `main`. Si realmente se requiere borrado físico, diseñar permisos, validación de referencias, auditoría y pruebas específicas antes de exponerlo.

## Pruebas solicitadas en Windows

```bat
git status
git fetch origin
git switch --track origin/integracion/avance-companero
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.productos.test_integracion_companero apps.productos.test_mermas apps.core.test_auditoria apps.usuarios.test_listado apps.usuarios.test_recuperacion apps.usuarios.test_email_backend
```

**No ejecutar** `seed --reset` ni migraciones contra Neon de producción durante la revisión.

## Pruebas manuales antes de despliegue

1. Abrir Dashboard en escritorio/móvil: sin valores falsos al inicio y carga dinámica.
2. Buscar SKU y nombre desde la lupa del Dashboard; debe filtrar el Catálogo.
3. Crear producto de prueba con código de barras, escanearlo con cámara y comprobar que se guarda.
4. Editar el mismo producto, conservar el código e incorporar otro; repetir lectura por SKU y código desde Movimientos.
5. Abrir el menú responsive y la campana en pantallas pequeñas; generar una entrada y verificar que aparece una notificación administradora.
6. Registrar una merma y verificar descuento de stock, historial y aviso; comprobar que usuarios ajenos no pueden marcar notificaciones de otros.
7. Repetir la suite de recuperación de contraseña y permisos; revisar que los datos existentes no se eliminan.
8. Ensayar migraciones primero sobre base desechable/branch aislada de Neon, no sobre `production`.

## Limitación

Las pruebas unitarias escritas en GitHub aún **no se ejecutaron en el entorno del usuario**. Esta rama y su PR permanecen en borrador hasta que pasen todas las comprobaciones.
