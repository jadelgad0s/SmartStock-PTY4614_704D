# SmartStock

**Sistema de Gestión de Inventario**

---

## Descripción

SmartStock es una plataforma web de gestión de inventario diseñada para pequeñas y medianas empresas del sector comercial que necesitan administrar de manera centralizada sus productos, bodegas, ubicaciones y movimientos de inventario.

El sistema permite:

- Registrar y administrar productos identificados por SKU y códigos de barras o QR.
- Configurar múltiples bodegas y representar su estructura mediante pasillos, estanterías, niveles y ubicaciones de almacenamiento, adaptándose a la organización física de cada empresa.
- Registrar entradas, salidas, transferencias entre bodegas y mermas, manteniendo un historial de movimientos para facilitar la trazabilidad.
- Generar alertas de stock mínimo, reportes y funcionalidades de apoyo al análisis del inventario.

El proyecto contempla una aplicación web y una aplicación de escritorio.

---

## Problema que resuelve

Muchas PYMEs gestionan su inventario de forma manual mediante planillas Excel o registros en papel. Esto provoca quiebres de stock no detectados a tiempo, pérdidas por diferencias de inventario no trazadas y la imposibilidad de conocer la cantidad y ubicación real de cada producto en sus bodegas. SmartStock centraliza y automatiza este proceso.

---

## Tecnologías utilizadas

| Componente              | Tecnología                                                                   |
|:------------------------|:-----------------------------------------------------------------------------|
| Lenguaje                | Python 3.13.7                                                                |
| Framework               | Django                                                                       |
| API interna             | Django REST (comunicación entre componentes web, escritorio y base de datos) |
| Frontend                | Django Templates, HTML, CSS, JavaScript                                      |
| Base de datos           | PostgreSQL 16                                                                |
| Aplicación de escritorio| pywebview                                                                    |
| Control de versiones    | Git, GitHub                                                                  |
| Gestión del proyecto    | Jira                                                                         |

---

## Arquitectura SmartStock
 
```
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │  
│   PC del Administrador            Celulares (Encargado / Operador)    │
│  ┌──────────────────────┐          ┌──────────────────────┐           │
│  │ SmartStock Desktop   │          │ Navegador móvil      │           │
│  │  (desktop.py)        │          │  (Chrome / Safari)   │           │
│  │                      │          │                      │           │
│  │  • pywebview         │          │  • Interfaz web      │           │
│  │  • Chromium embebido │          │  • Escáner cámara    │           │
│  │  • Acceso completo   │          │  • Notificaciones    │           │
│  └──────────┬───────────┘          └──────────┬───────────┘           │
│             │                                 │                       │
│             │ HTTP localhost:8000             │ HTTPS                 │
│             │                                 │                       │
│             └──────────┬──────────────────────┘                       │
│                        │                                              │
│                        ▼                                              │
│      ┌──────────────────────────────────────────────────┐             │
│      │            Django Backend                        │             │
│      │                                                  │             │
│      │  apps/core        apps/usuarios   apps/productos │             │
│      │  ──────────       ─────────────   ─────────────  │             │
│      │  • Modelos        • Usuario       • Producto     │             │
│      │    abstractos     • Rol/Permiso   • CodigoBarra  │             │
│      │  • Auditoría      • Sesión        • Bodega       │             │
│      │  • Middleware     • JWT auth      • StockBodega  │             │
│      │  • Responses      • Permisos      • Movimiento   │             │
│      │                    granulares     • Merma        │             │
│      │                                   • Alerta       │             │
│      │                                   • Notificación │             │
│      │                                                  │             │
│      │  DRF + SimpleJWT + CORS                          │             │
│      └──────────────┬───────────────────────────────────┘             │
│                     │                                                 │
│                     │ Django ORM (CONN_MAX_AGE=600)                   │
│                     │                                                 │
│                     ▼                                                 │
│      ┌──────────────────────────────────────────────────┐             │
│      │        PostgreSQL 16  ·  Neon Cloud              │             │
│      │                                                  │             │
│      │        30+ tablas normalizadas                   │             │
│      │                                                  │             │
│      │  Usuarios/Seguridad:  usuarios, roles, permisos, │             │
│      │                       rol_permiso, sesiones,     │             │
│      │                       auditoria                  │             │
│      │                                                  │             │
│      │  Productos:           productos, codigos_barra   │             │
│      │                                                  │             │
│      │  Bodegas:             bodegas, pasillos,         │             │
│      │                       estanterias, niveles,      │             │
│      │                       ubicaciones,               │             │
│      │                       producto_ubicacion         │             │
│      │                                                  │             │
│      │  Movimientos:         stock_bodega, stock_minimo,│             │
│      │                       movimientos,               │             │
│      │                       tipo_movimiento,           │             │
│      │                       detalle_movimiento,        │             │
│      │                       transferencias,            │             │
│      │                       detalle_transferencia,     │             │
│      │                       historial_movimientos      │             │
│      │                                                  │             │
│      │  Mermas:              mermas, motivo_merma       │             │
│      │                                                  │             │
│      │  Alertas:             alertas, tipo_alerta,      │             │
│      │                       log_alertas                │             │
│      │                                                  │             │
│      │  Notificaciones:      notificaciones             │             │
│      │                                                  │             │
│      │  Reportes:            reportes, tipo_reporte     │             │
│      └──────────────────────────────────────────────────┘             │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

La aplicación de escritorio es la herramienta principal del administrador. Mediante pywebview, abre una ventana nativa que carga la misma interfaz web servida por Django en localhost, dando acceso completo a todas las funcionalidades del sistema: gestión de productos, bodegas, ubicaciones, movimientos, alertas, reportes y administración de usuarios. Toda la lógica de negocio, validaciones y acceso a datos se concentra en el backend Django.

---

## Instrucciones para ejecutar el proyecto localmente

### Prerrequisitos

- Python 3.13.7
- PostgreSQL 16+
- Git

### Instalación

```bash
# Clonar el repositorio
git clone https://github.com/tu-usuario/SmartStock-PTY4614_704D.git
cd SmartStock-PTY4614_704D

# Crear y activar entorno virtual
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con los datos de conexión a PostgreSQL

# Crear la base de datos
createdb smartstock

# Aplicar migraciones
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser

# Ejecutar servidor de desarrollo
python manage.py runserver
```

Acceder a `http://127.0.0.1:8000/` en el navegador.

### Ejecutar la aplicación de escritorio

```bash
python desktop.py
```

---

## Integrantes del equipo

| Nombre                 | Rol          |
|:-----------------------|:-------------|
| Javier Delgado Sánchez | Product Owner|
| Iván Díaz              | Scrum Master |
| Joaquín Valenzuela     | Desarrollador|
| Angelo Figueroa        | Desarrollador|

---

## Metodología de trabajo

El equipo trabaja con Scrum:

- Sprints semanales con entregables incrementales.
- Ceremonias: Sprint Planning, Daily Standup, Sprint Review, Sprint Retrospective.
- Artefactos: Product Backlog, Sprint Backlog, Burndown Chart.
- Herramientas: Jira para gestión de tareas, GitHub para control de versiones.
- Estimación: Planning Poker con escala de Fibonacci (1, 2, 3, 5, 8, 13).
- Priorización: MoSCoW (Must have, Should have, Could have, Won't have).

---

## Estructura del repositorio

```
SmartStock-PTY4614_704D/
├── Fase 1/
│   ├── Evidencias Grupales/
│   │   ├── 1.4_APT122_FormativaFase1.docx
│   │   └── 1.5_GuiaEstudiante_Fase1_Definicion...
│   └── Evidencias Individuales/
│       ├── DELGADO_JAVIER_1.1_APT122_AutoevaluacionCompetenciasFase1.docx
│       ├── DELGADO_JAVIER_1.2_APT122_DiarioReflexionFase1.docx
│       ├── DELGADO_JAVIER_1.3_APT122_AutoevaluaciónFase1.docx
│       ├── DIAZ_IVAN_1.1_APT122_AutoevaluacionCompetenciasFase1.docx
│       ├── DIAZ_IVAN_1.2_APT122_DiarioReflexionFase1.docx
│       ├── DIAZ_IVAN_1.3_APT122_AutoevaluaciónFase1.docx
│       ├── FIGUEROA_ANGELO_1.1_APT122_AutoevaluacionCompetenciasFase1.docx
│       ├── FIGUEROA_ANGELO_1.2_APT122_DiarioReflexionFase1.docx
│       ├── FIGUEROA_ANGELO_1.3_APT122_AutoevaluaciónFase1.docx
│       ├── VALENZUELA_JOAQUIN_1.1_APT122_AutoevaluacionCompetenciasFase1.docx
│       ├── VALENZUELA_JOAQUIN_1.2_APT122_DiarioReflexionFase1.docx
│       └── VALENZUELA_JOAQUIN_1.3_APT122_AutoevaluaciónFase1.docx
├── Fase 2/
│   ├── Evidencias Grupales/
│   │   └── 2.4_GuiaEstudiante_Fase 2_DesarrolloProyecto APT.docx
│   ├── Evidencias Individuales/
│   │   ├── DELGADO_JAVIER_2.1_APT122_DiarioReflexionFase2.docx
│   │   ├── DIAZ_IVAN_2.1_APT122_DiarioReflexionFase2.docx
│   │   ├── FIGUEROA_ANGELO_2.1_APT122_DiarioReflexionFase2.docx
│   │   └── VALENZUELA_JOAQUIN_2.1_APT122_DiarioReflexionFase2.docx
│   └── Evidencias Proyecto/
│       ├── Evidencias de documentación/
│       └── Evidencias de sistema/
├── Fase 3/
│   ├── Evidencias Grupales/
│   └── Evidencias Individuales/
└── README.md
```

---

Proyecto académico — Portafolio de Título - Grupo 8, Ingeniería en Informática, Duoc UC.
