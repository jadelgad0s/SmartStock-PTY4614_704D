# Alertas de stock por SMS con Twilio

Esta integración envía SMS reales y **Twilio cobra por utilizarlos**. Está activa por defecto para las pruebas y demostraciones de SmartStock, con un límite de 100 intentos diarios. Requiere credenciales, remitente y destinatarios válidos para realizar envíos. No requiere WhatsApp, Redis, Celery ni un servicio adicional de Render.

## Comportamiento

- Usa el stock y el mínimo de **cada producto en cada bodega**, con el mismo cálculo de Catálogo y Dashboard: suma de existencias y máximo de los mínimos antiguos duplicados.
- Stock bajo: `0 < stock <= mínimo`, si el mínimo es mayor que cero. Agotado: `stock <= 0`, incluso con mínimo cero.
- Evalúa salidas, entradas, mermas y cambios de mínimo guardados desde la API. No envía SMS al abrir una página ni por cada recarga.
- Por ciclo, envía como máximo una alerta de stock bajo y otra de agotado a cada destinatario. Una reposición parcial no repite la alerta. Cuando el stock supera el mínimo se habilita un nuevo ciclo.
- Si activas la integración con productos que ya están críticos, su primera operación evaluada puede generar un aviso. No hay envío masivo automático de todo el catálogo al activar la variable.
- Un producto o bodega inactivos no generan envíos. Antes de enviar un pendiente se vuelve a comprobar el stock, la vigencia del ciclo y el destinatario.
- Se registra el pendiente junto con la operación de inventario. El envío ocurre **después de confirmar la transacción**. Si inventario o auditoría fallan, no se envía. Un fallo de Twilio conserva el inventario confirmado y queda registrado en el historial SMS.

## Texto de las alertas

El mensaje indica qué producto reponer y en qué bodega, y explica las existencias respecto del mínimo en una frase completa. Separa el aviso, la instrucción y el SKU en bloques para facilitar la lectura en el celular. Por ejemplo:

```text
SmartStock: stock bajo

Reponer Bebida Cherry Lata Coca-Cola 355 ml en Bodega Central.
Quedan 5 unidades. El minimo es 5.

SKU 4564774647
STOP para salir.
```

Al quedar una unidad dice «Queda 1 unidad». Cuando se agota el producto, el encabezado cambia a «SmartStock: agotado», muestra las unidades restantes y conserva la instrucción de reponer en la bodega correspondiente.

El cuerpo generado usa hasta 160 caracteres GSM básicos, con saltos de línea y sin emojis ni tildes que obliguen a usar Unicode. Si falta espacio, primero se quitan las líneas en blanco. Con datos extensos se usa un formato compacto que separa el producto, la bodega y «Stock: cantidad. Minimo: cantidad»; los nombres se acortan con `...` solo cuando hace falta. Se conservan el SKU completo, las cantidades y la instrucción STOP.

La frase **“Sent from your Twilio trial account”** de los SMS de prueba la añade Twilio; no forma parte del cuerpo generado por SmartStock y no se puede quitar desde la aplicación. Para eliminarla hay que actualizar la cuenta de Twilio. Ese prefijo u otros textos añadidos por el proveedor pueden aumentar la longitud recibida y el número de segmentos. Los SMS ya enviados conservan su mensaje original en el historial; el texto nuevo se aplica a las próximas alertas y a los pendientes que se envíen después de actualizar el código.

## Configuración en Render

Primero instala las dependencias y aplica las migraciones de esta versión. En el servicio web, abre **Environment** y agrega variables privadas:

| Variable | Valor |
| --- | --- |
| `SMS_ALERTAS_ACTIVAS` | `True` para mantener los envíos activos en pruebas y demostraciones. Es el valor por defecto. `False` permite pausarlos expresamente. |
| `SMS_ALERTAS_DESTINATARIOS` | De 1 a 3 móviles chilenos que hayan autorizado recibir estos avisos, separados por coma, en formato `+569XXXXXXXX`. |
| `SMS_ALERTAS_LIMITE_DIARIO` | `100` por defecto. Cuenta intentos para todos los destinatarios, incluidos rechazos e intentos inciertos. Día de `America/Santiago`. |
| `SMS_ALERTAS_TIMEOUT` | `3` segundos por solicitud por defecto. Permitido entre 1 y 5. |
| `TWILIO_ACCOUNT_SID` | SID de la cuenta (`AC…`). |
| `TWILIO_AUTH_TOKEN` | Token secreto de Twilio. Nunca incluirlo en Git, capturas, la interfaz o mensajes. |
| `TWILIO_MESSAGING_SERVICE_SID` | Servicio (`MG…`) con un remitente SMS configurado. Si se define, tiene prioridad. |
| `TWILIO_FROM_NUMBER` | Alternativa al servicio: número Twilio con capacidad de envío SMS, en formato internacional. No es el celular destinatario. |
| `TWILIO_PUBLIC_BASE_URL` | `https://smartstockchile.cl`. En otro ambiente, su propio origen HTTPS público, sin rutas. |

El remitente debe estar habilitado para enviar a Chile. Revisa en Twilio las **SMS Geo Permissions**, saldo, requisitos del remitente y disponibilidad de la ruta. Un número guardado en SmartStock no se convierte automáticamente en destinatario SMS: solo se envía a los números configurados explícitamente.

Twilio anuncia una prueba limitada; no es un plan gratuito permanente. Su documentación vigente restringe además el contenido personalizado durante la prueba. Para alertas reales con nombre, stock y bodega, confirma que tu cuenta permite ese contenido y el envío a Chile antes de activarla.

Las credenciales y los destinatarios se leen únicamente en el servidor. La API administrativa muestra teléfonos enmascarados, nunca el token. Actualiza variables y vuelve a desplegar para cambiar destinatarios, límite o activación.

Para mantener las demostraciones activas, guarda estos valores en **Render → Environment**:

```env
SMS_ALERTAS_ACTIVAS=True
SMS_ALERTAS_LIMITE_DIARIO=100
SMS_ALERTAS_TIMEOUT=3
TWILIO_PUBLIC_BASE_URL=https://smartstockchile.cl
```

Configura también las credenciales, el remitente y los destinatarios privados que ya probaste localmente. El `.env` de tu PC no se copia a Render al fusionar un PR. Una variable `SMS_ALERTAS_ACTIVAS=False` guardada en Render tiene prioridad sobre el valor por defecto del código: cámbiala a `True` y vuelve a desplegar. La URL pública de producción debe ser la del sitio; el túnel ngrok se usa únicamente para las pruebas locales.

## Consultar desde la API

Requiere JWT de un administrador activo, igual que Auditoría:

| Método y ruta | Uso |
| --- | --- |
| `GET /api/v1/alertas-sms/estado/` | Activación, configuración pendiente, destinatarios enmascarados, cuota usada y pendientes. |
| `GET /api/v1/alertas-sms/historial/` | Historial de 25 envíos por página; `?page=2` y `?estado=ENTREGADO` son opcionales. |
| `POST /api/v1/alertas-sms/procesar-pendientes/` | Revisa hasta 3 pendientes. **Puede generar cargos.** Respeta la cuota y no repite envíos en curso, aceptados o inciertos. |

El historial también está disponible, en modo de lectura, en **Configuración avanzada → Envíos de alertas SMS** del administrador de Django para las cuentas con permiso de consulta del modelo.

## Entrega y callbacks

Cada envío incluye automáticamente su URL de callback. Twilio publica estados en:

`POST https://smartstockchile.cl/api/v1/alertas-sms/twilio/estado/<id-del-envío>/`

La aplicación valida `X-Twilio-Signature` con la librería oficial, la URL pública exacta, la cuenta, el teléfono cuando viene incluido y el SID del mensaje. Este endpoint no usa el JWT de SmartStock. No requiere agregar una URL de callback manual a cada número de Twilio.

**Aceptado por Twilio** no significa entregado al celular. El historial diferencia aceptado, enviado a la red, entregado, no entregado, rechazado y resultado por confirmar. Los callbacks repetidos o atrasados no hacen retroceder el estado.

## Cuota, reintentos y pendientes

- El cuerpo generado se limita a 160 caracteres GSM básicos, sin tildes, para evitar varios segmentos por Unicode o longitud. Conserva SKU, bodega, stock y mínimo; los nombres largos se acortan. Los textos adicionales del proveedor no están incluidos en este límite. Twilio mantiene el control final de cargos y entrega.
- El límite diario es compartido por todos los procesos del servidor. No limita los cobros mensuales del número, impuestos u otros usos que hagas en la misma cuenta de Twilio.
- Al alcanzar el límite, los pendientes se conservan. No se descartan ni se reenvían todos al reiniciar Render.
- Solo un rechazo explícito por exceso de solicitudes (`HTTP 429`) queda pendiente para otro intento, después de un minuto y hasta 3 intentos en total. No hay un bucle de reintentos automáticos.
- Un timeout, desconexión, error de servidor o proceso interrumpido puede haber alcanzado a Twilio. Se deja **Resultado por confirmar**, sin reenvío automático para evitar mensajes y cobros duplicados. Un callback válido puede completar ese resultado.
- Los rechazos definitivos no se reintentan. El código `21610` indica que el destinatario se dio de baja. No se omite ni se intenta evadir esa baja.
- Para revisar pendientes tras corregir la configuración, liberar cuota o esperar un `429`, un administrador puede usar la API anterior o ejecutar:

```console
python manage.py procesar_alertas_sms
```

El comando procesa un lote máximo de 3. Si quedan pendientes, puede repetirse. No depende de que el servicio gratuito de Render permanezca despierto: las operaciones nuevas intentan enviar sus SMS después del commit; los pendientes requieren ejecutar este comando o el endpoint. No incluye un programador periódico ni promete entrega durante una caída del servidor o del proveedor.

## Prueba local y activación

En CMD de Windows, dentro del repositorio:

```bat
call venv\Scripts\activate.bat
python -m pip install -r requirements-web.txt
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
```

Los tests usan un proveedor simulado: **no envían SMS reales ni consumen saldo**. Para probar callbacks reales localmente necesitas un origen HTTPS público y configurar `TWILIO_PUBLIC_BASE_URL` con ese origen.

Para ejecutar el resto de la suite con tus credenciales reales presentes en el `.env`, pausa los SMS solo en el CMD donde corres las pruebas:

```bat
set "SMS_ALERTAS_ACTIVAS=False"
python manage.py test
set "SMS_ALERTAS_ACTIVAS=True"
```

Con la cuenta y el remitente ya preparados, configura un único celular autorizado y conserva `SMS_ALERTAS_ACTIVAS=True` para las demostraciones. En un producto de prueba con 6 unidades, guarda mínimo 5 y registra una salida de 1: debe aparecer un único SMS de stock bajo. Otra salida sin llegar a cero no repite el aviso. Al llegar a cero se genera la alerta de agotado. Comprueba la entrega en el historial y en la consola de Twilio. Estas pruebas reales tienen costo.

## Referencias oficiales

- [Precio SMS a Chile](https://www.twilio.com/en-us/sms/pricing/cl)
- [Límites de la prueba de Twilio](https://www.twilio.com/docs/usage/trials)
- [Texto añadido por Twilio a los SMS de prueba](https://www.twilio.com/en-us/blog/receive-notifications-java-prometheus-spring-boot-sms0)
- [Codificación y segmentos SMS](https://www.twilio.com/docs/glossary/what-sms-character-limit)
- [API de mensajes y estados](https://www.twilio.com/docs/messaging/api/message-resource)
- [Validación de firmas en Django](https://www.twilio.com/docs/usage/tutorials/how-to-secure-your-django-project-by-validating-incoming-twilio-requests)
