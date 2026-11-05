# Gestión de alertas SMS pendientes

Los administradores tienen una pantalla **Sistema → Alertas SMS**, disponible en `/alertas-sms/`. Los envíos nuevos mantienen su intento automático habitual. La pantalla permite revisar y procesar pendientes sin usar CMD.

## Revisar y procesar

1. Revisa el estado del servicio, los destinatarios enmascarados y los intentos disponibles del día. La pantalla consulta la configuración del servidor; no cambia variables de entorno.
2. Filtra el historial por estado, producto, SKU, bodega, código de error o fechas. Inicialmente muestra los pendientes. Las fechas se interpretan en la zona horaria indicada en la pantalla e incluyen todo el día final.
3. Abre **Ver detalle** para consultar el mensaje, los intentos, el próximo intento y el motivo de espera.
4. Pulsa **Procesar pendientes** para preparar hasta **3 avisos** que coincidan con los filtros y con la cuota disponible. La vista previa es una consulta: todavía no envía mensajes.
5. Comprueba los avisos y pulsa **Confirmar procesamiento**. El servidor revisa únicamente los identificadores confirmados. También puedes preparar un solo aviso desde su detalle.
6. Consulta el resultado. **Aceptado por Twilio** no confirma la entrega al celular. Los cambios posteriores de entrega se reciben mediante el callback de Twilio; puedes usar **Actualizar** para volver a consultarlos.

Cada procesamiento vuelve a comprobar el stock, la vigencia del ciclo de alerta, el estado, la espera entre intentos, el máximo de 3 intentos y la cuota diaria. Los avisos cuyo stock se recuperó pueden cancelarse automáticamente sin llamar a Twilio. Una solicitud de procesamiento queda registrada en Auditoría y en las notificaciones de la aplicación, sin afirmar que el SMS fue entregado.

## Esperas y resultados inciertos

- **Pendiente:** aún puede estar esperando el próximo intento o la cuota del día. El detalle explica la condición.
- **Envío en curso / Resultado por confirmar:** la pantalla no permite forzar un reenvío. Un identificador de Twilio conocido también impide otro intento de envío.
- **Servicio pausado, configuración incompleta o cuota agotada:** puedes consultar el historial; el procesamiento queda bloqueado.
- **Conexión interrumpida al confirmar:** se debe actualizar el historial para comprobar el resultado. La interfaz no repite automáticamente la solicitud ni prepara otro lote.

Abrir, filtrar, actualizar o consultar la vista previa no procesa mensajes. La función manual no instala un programador de tareas ni un servicio en segundo plano: la revisión de pendientes se solicita desde esta pantalla.

## Cancelar un aviso

Desde **Ver detalle → Cancelar aviso** puedes confirmar la cancelación de un pendiente que aún no tenga identificador de Twilio. La cancelación conserva su historial y el stock, y queda auditada. No reinicia el ciclo de stock bajo ni provoca otro SMS para reemplazar el cancelado. No se ofrece cancelar un mensaje que ya salió hacia el proveedor.

## Acceso y compatibilidad

- Requiere una cuenta activa de administrador y, si tiene rol asignado, un rol activo.
- No muestra credenciales de Twilio ni teléfonos completos.
- Mantiene el comando existente y el endpoint anterior de procesamiento; el cuerpo `{}` continúa revisando hasta 3 pendientes globales. La pantalla utiliza `{ "ids": ["UUID", "..."] }` para confirmar avisos concretos.
- No requiere migraciones ni cambios de configuración. Mantiene `SMS_ALERTAS_ACTIVAS`, destinatarios, cuota y timeout del entorno actual.
- Procesar puede consumir saldo de Twilio. Las pruebas de desarrollo utilizan datos ficticios y un cliente simulado; no envían SMS reales.

## Prueba local en Windows CMD

Antes de la integración del PR, puedes revisar la rama así desde el repositorio, con el entorno virtual activado y sin cambios locales pendientes:

```bat
git fetch origin
git switch --track origin/mejora/gestion-sms-pendientes
python manage.py check
python manage.py runserver
```

Si ya tienes esa rama local:

```bat
git switch mejora/gestion-sms-pendientes
git pull --ff-only
python manage.py check
python manage.py runserver
```

Inicia sesión como administrador y abre `http://127.0.0.1:8000/alertas-sms/`. Para probar solo la revisión, abre el historial y sus detalles sin confirmar el procesamiento.
