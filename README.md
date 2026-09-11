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
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SMARTSTOCK                                     │
│                                                                             │
│  ┌───────────────────────┐            ┌───────────────────────────────┐     │
│  │   App de Escritorio   │            │       Aplicación Web          │     │
│  │     (pywebview)       │            │   (Django Templates + JS)     │     │
│  │                       │  HTTP      │                               │     │
│  │  Ventana nativa que   ├───────────►│  /admin/  Panel de admin      │     │
│  │  carga la interfaz    │ localhost  │  /login/  Autenticación       │     │
│  │  web del admin        │            │                               │     │
│  └───────────────────────┘            └───────────────┬───────────────┘     │
│                                                       │                     │
│                                                       │                     │
│                                 ┌─────────────────────▼──────────────────┐  │
│                                 │         Django Backend                 │  │
│                                 │                                        │  │
│                                 │  ┌────────────┐  ┌──────────────────┐  │  │
│                                 │  │  Usuarios  │  │    Productos     │  │  │
│                                 │  │  y Roles   │  │    SKU, Códigos  │  │  │
│                                 │  └────────────┘  └──────────────────┘  │  │
│                                 │                                        │  │
│                                 │  ┌────────────┐  ┌──────────────────┐  │  │
│                                 │  │  Bodegas   │  │   Ubicaciones    │  │  │
│                                 │  │  Múltiples │  │   Pasillos       │  │  │
│                                 │  │            │  │   Estanterías    │  │  │
│                                 │  └────────────┘  │   Niveles        │  │  │
│                                 │                  └──────────────────┘  │  │
│                                 │  ┌────────────┐  ┌──────────────────┐  │  │
│                                 │  │Movimientos │  │    Alertas       │  │  │
│                                 │  │ Entradas   │  │    Stock mínimo  │  │  │
│                                 │  │ Salidas    │  └──────────────────┘  │  │
│                                 │  │ Transfer.  │                        │  │
│                                 │  │ Mermas     │  ┌──────────────────┐  │  │
│                                 │  │ Historial  │  │    Reportes      │  │  │
│                                 │  └────────────┘  │    Inventario    │  │  │
│                                 │                  └──────────────────┘  │  │
│                                 │                                        │  │
│                                 │  ORM: Django ORM                       │  │
│                                 │  Auth: admin, encargado, operador      │  │
│                                 └──────────────────┬─────────────────────┘  │
│                                                    │                        │
│                                                    │ Django ORM             │
│                                                    │                        │
│                                 ┌──────────────────▼─────────────────────┐  │
│                                 │          PostgreSQL 16                 │  │
│                                 │     (30 tablas normalizadas)           │  │
│                                 │                                        │  │
│                                 │  Usuarios y seguridad:                 │  │
│                                 │    usuarios, roles, permisos,          │  │
│                                 │    rol_permiso, sesiones               │  │
│                                 │                                        │  │
│                                 │  Productos:                            │  │
│                                 │    productos, codigos_barra            │  │
│                                 │                                        │  │
│                                 │  Bodegas y ubicaciones:                │  │
│                                 │    bodegas, pasillos, estanterias,     │  │
│                                 │    niveles, ubicaciones,               │  │
│                                 │    producto_ubicacion                  │  │
│                                 │                                        │  │
│                                 │  Stock y movimientos:                  │  │
│                                 │    stock_bodega, stock_minimo,         │  │
│                                 │    movimientos, tipo_movimiento,       │  │
│                                 │    detalle_movimiento, transferencias, │  │
│                                 │    detalle_transferencia, mermas,      │  │
│                                 │    motivo_merma,                       │  │
│                                 │    historial_movimientos               │  │
│                                 │                                        │  │
│                                 │  Alertas y reportes:                   │  │
│                                 │    alertas, tipo_alerta, log_alertas,  │  │
│                                 │    reportes, tipo_reporte, auditoria   │  │
│                                 │                                        │  │
│                                 └────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
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
│       ├── Delgado_Javier_1.1_APT122_AutoevaluacionCompetenciasFase1.docx
│       ├── Delgado_Javier_1.2_APT122_DiarioReflexionFase1.docx
│       ├── Delgado_Javier_1.3_APT122_AutoevaluaciónFase1.docx
│       ├── Díaz_Iván_1.1_APT122_AutoevaluacionCompetenciasFase1.docx
│       ├── Díaz_Iván_1.2_APT122_DiarioReflexionFase1.docx
│       ├── Díaz_Iván_1.3_APT122_AutoevaluaciónFase1.docx
│       ├── Figueroa_Angelo_1.1_APT122_AutoevaluacionCompetenciasFase1.docx
│       ├── Figueroa_Angelo_1.2_APT122_DiarioReflexionFase1.docx
│       ├── Figueroa_Angelo_1.3_APT122_AutoevaluaciónFase1.docx
│       ├── Valenzuela_Joaquín_1.1_APT122_AutoevaluacionCompetenciasFase1.docx
│       ├── Valenzuela_Joaquín_1.2_APT122_DiarioReflexionFase1.docx
│       └── Valenzuela_Joaquín_1.3_APT122_AutoevaluaciónFase1.docx
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

Proyecto académico — Portafolio de Título - Grupo 8, Ingeniería en Informática, Duoc UC.
