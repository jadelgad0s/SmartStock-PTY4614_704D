# SmartStock

## Sistema de Gestión de Inventario

### Descripción

SmartStock es una plataforma web de gestión de inventario diseñada para pequeñas y medianas empresas del sector comercial que necesitan administrar de manera centralizada sus productos, bodegas, ubicaciones y movimientos de inventario.

El sistema permite:

- Registrar y administrar productos identificados por SKU y códigos de barras o QR, con autocompletado desde la base pública Open Food Facts.
- Configurar múltiples bodegas y representar su estructura mediante pasillos, estanterías, niveles y ubicaciones de almacenamiento, adaptándose a la organización física de cada empresa.
- Registrar entradas, salidas, transferencias entre bodegas y mermas, manteniendo un historial de movimientos para facilitar la trazabilidad.
- Generar alertas internas y alertas SMS reales mediante Twilio cuando el stock baja o se agota.
- Enviar correos de recuperación de contraseña vía API HTTPS.
- Dashboard de KPIs, reportes de inventario, Kardex por producto y auditoría completa de todas las acciones del sistema.

El proyecto contempla una aplicación web desplegada en producción y una aplicación de escritorio para el administrador.

### Problema que resuelve

Muchas PYMEs gestionan su inventario de forma manual mediante planillas Excel o registros en papel. Esto provoca quiebres de stock no detectados a tiempo, pérdidas por diferencias de inventario no trazadas y la imposibilidad de conocer la cantidad y ubicación real de cada producto en sus bodegas. SmartStock centraliza y automatiza este proceso, notificando por SMS en tiempo real cuando se requiere reponer.

## Tecnologías

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.13 |
| Framework web | Django 5.2 |
| API REST | Django REST Framework |
| Autenticación | SimpleJWT (access + refresh con blacklist y CHECK_REVOKE_TOKEN) |
| Base de datos | PostgreSQL 16 (Neon Cloud en producción) |
| ORM | Django ORM con CONN_MAX_AGE=600 para pooling |
| Aplicación de escritorio | SmartStock.exe (PyInstaller + pywebview + Microsoft WebView2) |
| Frontend | Django Templates + Bootstrap 5.3 + JavaScript vanilla |
| Gráficos | Chart.js |
| Escáner móvil | html5-qrcode (EAN, UPC, Code128, QR) |
| SMS reales | Twilio (con callback firmado por X-Twilio-Signature) |
| Email transaccional | Resend (API HTTPS, backend personalizado) |
| Catálogo externo | Open Food Facts API (con caché y cupo compartido) |
| Archivos estáticos | Whitenoise (compresión + hash de caché) |
| Servidor WSGI | Gunicorn |
| Deploy | smartstockchile.cl en Render con HTTPS (Cloudflare) |
| Base de datos cloud | dj-database-url + DATABASE_URL |
| Variables de entorno | python-decouple |
| Control de versiones | Git + GitHub |
| Gestión de proyecto | Jira (Scrum) |

## Arquitectura SmartStock

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   PC del Administrador              Celulares (Encargado / Operador)        │
│  ┌──────────────────────┐           ┌──────────────────────┐                │
│  │  SmartStock.exe      │           │ Navegador móvil      │                │
│  │  (PyInstaller)       │           │  (Chrome / Safari)   │                │
│  │                      │           │                      │                │
│  │  • pywebview         │           │  • Interfaz web      │                │
│  │  • Microsoft         │           │  • Escáner cámara    │                │
│  │    WebView2          │           │    (html5-qrcode)    │                │
│  │   (gui=edgechromium) │           │  • Notificaciones    │                │
│  │  • Ventana nativa    │           │                      │                │
│  └──────────┬───────────┘           └──────────┬───────────┘                │
│             │                                  │                            │
│             │ HTTPS                            │ HTTPS                      │
│             │ smartstockchile.cl               │ smartstockchile.cl         │
│             │                                  │                            │
│             └──────────┬───────────────────────┘                            │
│                        │                                                    │
│                        ▼                                                    │
│                ┌──────────────┐                                             │
│                │  Cloudflare  │                                             │
│                │  (DNS + SSL) │                                             │
│                └──────┬───────┘                                             │
│                       │                                                     │
│                       ▼                                                     │
│                ┌──────────────┐                                             │
│                │ Render Cloud │                                             │
│                │ (Gunicorn +  │                                             │
│                │  Whitenoise) │                                             │
│                └──────┬───────┘                                             │
│                       │                                                     │
│                       ▼                                                     │
│      ┌─────────────────────────────────────────────────────┐                │
│      │              Django 5.2 Backend                     │                │
│      │        API REST  /api/v1/ (45+ endpoints) + JWT     │                │
│      │                                                     │                │
│      │  apps/core        apps/usuarios      apps/productos │                │
│      │  ──────────       ─────────────      ─────────────  │                │
│      │  • Modelos        • Usuario          • Producto     │                │
│      │    abstractos     • Rol / Permiso    • CodigoBarra  │                │
│      │  • Auditoría      • RolPermiso       • Bodega       │                │
│      │    transversal    • Sesion           • StockBodega  │                │
│      │  • Middleware     • JWT              • Movimiento   │                │
│      │  • safe_delete      (SimpleJWT)      • Merma        │                │
│      │  • Responses      • Permisos         • Transferencia│                │
│      │    uniformes        granulares (24)  • Alerta       │                │
│      │                   • Email backend    • Notificación │                │
│      │                   • Recuperación     • Reporte      │                │
│      │                     por token        • SMS Twilio   │                │
│      │                                      • Consulta     │                │
│      │                                        externa      │                │
│      │                                                     │                │
│      │  DRF + SimpleJWT + django-cors-headers + Twilio SDK │                │
│      └──┬───────────────────────┬──────────────────────┬───┘                │
│         │                       │                      │                    │
│         │ Django ORM            │ HTTPS                │ HTTPS              │
│         │ (psycopg 3.2,         │                      │                    │
│         │ CONN_MAX_AGE=600)     │                      │                    │
│         │                       ▼                      ▼                    │
│         │               ┌──────────────┐       ┌──────────────┐             │
│         │               │   Twilio     │       │   Resend     │             │
│         │               │   (SMS)      │       │   (Email)    │             │
│         │               └──────┬───────┘       └──────────────┘             │
│         │                      │                                            │
│         │                      │ Callback firmado                           │
│         │                      │ X-Twilio-Signature                         │
│         │                      └──> smartstockchile.cl                      │
│         │                           /api/v1/alertas-sms/twilio/estado/      │
│         │                                                                   │
│         │               ┌──────────────┐                                    │
│         │               │ Open Food    │                                    │
│         ├──────────────>│  Facts API   │ (caché 1 día + cupo 12/min)        │
│         │               └──────────────┘                                    │
│         ▼                                                                   │
│      ┌─────────────────────────────────────────────────────┐                │
│      │       PostgreSQL 16  ·  Neon Cloud (AWS US-East)    │                │
│      │                                                     │                │
│      │              36 tablas normalizadas (3FN)           │                │
│      │                                                     │                │
│      │  Usuarios / Seguridad:  usuarios, roles, permisos,  │                │
│      │                         rol_permiso, sesiones,      │                │
│      │                         auditoria                   │                │
│      │                                                     │                │
│      │  Productos:             productos, codigos_barra,   │                │
│      │                         fichas_producto_externas,   │                │
│      │                         cupos_consulta_externa      │                │
│      │                                                     │                │
│      │  Bodegas:               bodegas, pasillos,          │                │
│      │                         estanterias, niveles,       │                │
│      │                         ubicaciones,                │                │
│      │                         producto_ubicacion          │                │
│      │                                                     │                │
│      │  Movimientos:           stock_bodega, stock_minimo, │                │
│      │                         tipo_movimiento,            │                │
│      │                         movimientos,                │                │
│      │                         detalle_movimiento,         │                │
│      │                         transferencias,             │                │
│      │                         detalle_transferencia,      │                │
│      │                         historial_movimientos       │                │
│      │                                                     │                │
│      │  Mermas:                mermas, motivo_merma        │                │
│      │                                                     │                │
│      │  Alertas:               alertas, tipo_alerta,       │                │
│      │                         log_alertas                 │                │
│      │                                                     │                │
│      │  SMS (Twilio):          envios_alertas_sms,         │                │
│      │                         estado_stock_sms,           │                │
│      │                         limite_diario_sms           │                │
│      │                                                     │                │
│      │  Notificaciones:        notificaciones              │                │
│      │                                                     │                │
│      │  Reportes:              reportes, tipo_reporte      │                │
│      └─────────────────────────────────────────────────────┘                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

La aplicación de escritorio se distribuye como **SmartStock.exe**, empaquetado con **PyInstaller**. Al ejecutarlo, **pywebview** abre una ventana nativa de Windows usando **Microsoft WebView2** como motor de renderizado (forzado con `gui='edgechromium'`) y carga directamente la aplicación desplegada en producción en smartstockchile.cl. El usuario no necesita Python ni dependencias instaladas — solo el WebView2 Runtime, que viene preinstalado en Windows 10/11.

## Módulos principales

### Autenticación y Seguridad
- JWT con access (60 min) + refresh (7 días) y rotación con blacklist
- PBKDF2 para hashing de contraseñas
- Bloqueo por 5 intentos fallidos (15 min)
- 24 permisos granulares en 7 módulos
- 3 roles predefinidos: administrador, encargado_bodega, operador
- Soft delete universal con validación de relaciones (`safe_delete`)
- Auditoría transversal via middleware (IP, user-agent, usuario, timestamp)
- Recuperación de contraseña por email con token de un solo uso

### Gestión de Inventario
- CRUD de productos con SKU único, códigos de barras/QR y autocompletado externo
- Jerarquía de bodegas: Bodega → Pasillo → Estantería → Nivel → Ubicación
- Control de stock por bodega con constraints de integridad
- Stock mínimo configurable por producto y bodega
- Dashboard con KPIs en tiempo real

### Movimientos
- Entradas, salidas, transferencias entre bodegas
- Mermas con motivo y observación
- Historial unificado de movimientos
- Validación de stock con `SELECT FOR UPDATE` para concurrencia

### Alertas SMS con Twilio
- Cola persistente de SMS procesada después del commit
- Cuota diaria compartida
- Ciclos por producto/bodega para no repetir avisos
- Callback de estado con firma `X-Twilio-Signature`
- Mensajes compactos de hasta 160 caracteres GSM
- Manejo de rate-limit (429) con reintentos acotados

### Reportes
- Kardex por producto con saldo histórico
- Inventario valorizado
- Exportación a CSV y PDF
- Reportes de auditoría con filtros

## APIs expuestas

El backend expone **45+ endpoints REST** bajo el prefijo `/api/v1/`:

- `/auth/` → login, logout, refresh, me, cambiar-password
- `/usuarios/` → CRUD + roles + permisos
- `/productos/` → CRUD + búsqueda + consulta externa
- `/bodegas/` + `/ubicaciones/` → gestión física
- `/alertas-sms/` → 9 endpoints (estado, historial, procesar, callback Twilio)
- `/auditoria/` → 6 endpoints (listar, exportar, reporte)
- `/reportes/` → Kardex y stock

## APIs externas consumidas

| Servicio | Uso |
|---|---|
| **Twilio** | Envío de SMS reales con callback firmado |
| **Open Food Facts** | Autocompletar productos por GTIN (con caché y cupo) |
| **Resend** | Emails transaccionales vía API HTTPS |

## Instrucciones para ejecutar el proyecto localmente

### Prerrequisitos

- Python 3.13.7
- PostgreSQL 16+
- Git

### Instalación

```bash
# 1. Clonar el repositorio

# 2. Crear y activar el entorno virtual
python -m venv venv
source venv/bin/activate        # Linux / Mac
venv\Scripts\activate           # Windows

# 3. Instalar las dependencias
pip install -r requirements.txt

# 4. Configurar las variables de entorno
cp .env.example .env
# Editar el .env con las credenciales correspondientes

# 5. Aplicar las migraciones
python manage.py migrate

# 6. (Opcional) Cargar datos iniciales
python manage.py seed

# 7. Crear un superusuario para acceder al admin
python manage.py createsuperuser

# 8. Levantar el servidor web
python manage.py runserver
# → http://127.0.0.1:8000

# 9. (Opcional) Levantar la aplicación de escritorio en modo desarrollo
python desktop.py
```

### Aplicación de escritorio en producción

El ejecutable `SmartStock.exe` se distribuye compilado con PyInstaller. Al abrirlo carga directamente **smartstockchile.cl** en una ventana nativa con WebView2. No requiere Python ni configuración adicional.

## Metodología de trabajo

El equipo trabaja con **Scrum**:

- Sprints semanales con entregables incrementales.
- Ceremonias: Sprint Planning, Daily Standup, Sprint Review, Sprint Retrospective.
- Artefactos: Product Backlog, Sprint Backlog, Burndown Chart.
- Herramientas: Jira para gestión de tareas, GitHub para control de versiones.
- Estimación: Planning Poker con escala de Fibonacci (1, 2, 3, 5, 8, 13).
- Priorización: MoSCoW (Must have, Should have, Could have, Won't have).

## Estructura del repositorio

```
SmartStock-PTY4614_704D/
├── Fase 1/
│   ├── Evidencias Grupales/
│   └── Evidencias Individuales/
├── Fase 2/
│   ├── Evidencias Grupales/
│   ├── Evidencias Individuales/
│   └── Evidencias Proyecto/
│       ├── Evidencias de documentación/
│       └── Evidencias de sistema/
├── Fase 3/
│   ├── Evidencias Grupales/
│   └── Evidencias Individuales/
└── README.md
```

---

**Proyecto académico** — Portafolio de Título - Grupo 8, Ingeniería en Informática, Duoc UC.
