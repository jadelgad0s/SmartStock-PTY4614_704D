"""
Comando de seeding para poblar la base de datos con datos iniciales.

Uso:
    python manage.py seed              # Crea todos los datos iniciales
    python manage.py seed --reset      # Elimina datos existentes y recrea

Datos que crea:
- Permisos base del sistema (agrupados por módulo)
- Roles del sistema: administrador, encargado_bodega, operador
- Un superusuario administrador de prueba (admin@smartstock.cl / Admin1234!)
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.usuarios.models import Usuario, Rol, Permiso


# === CATÁLOGO DE PERMISOS ===
# Estructura: (modulo, [(codigo, nombre, descripcion), ...])
PERMISOS_CATALOGO = [
    ('usuarios', [
        ('ver_usuario', 'Ver usuarios', 'Consultar listado y detalle de usuarios'),
        ('crear_usuario', 'Crear usuarios', 'Registrar nuevos usuarios en el sistema'),
        ('editar_usuario', 'Editar usuarios', 'Modificar datos de usuarios existentes'),
        ('desactivar_usuario', 'Desactivar usuarios', 'Desactivar cuentas de usuario'),
        ('gestionar_roles', 'Gestionar roles', 'Crear, editar y asignar roles'),
    ]),
    ('productos', [
        ('ver_producto', 'Ver productos', 'Consultar catálogo de productos'),
        ('crear_producto', 'Crear productos', 'Registrar nuevos productos'),
        ('editar_producto', 'Editar productos', 'Modificar productos existentes'),
        ('eliminar_producto', 'Eliminar productos', 'Desactivar productos'),
    ]),
    ('bodegas', [
        ('ver_bodega', 'Ver bodegas', 'Consultar bodegas y su estructura'),
        ('crear_bodega', 'Crear bodegas', 'Registrar nuevas bodegas'),
        ('editar_bodega', 'Editar bodegas', 'Modificar bodegas y ubicaciones'),
        ('eliminar_bodega', 'Eliminar bodegas', 'Desactivar bodegas'),
    ]),
    ('movimientos', [
        ('ver_movimiento', 'Ver movimientos', 'Consultar movimientos de inventario'),
        ('registrar_entrada', 'Registrar entradas', 'Registrar entradas de mercadería'),
        ('registrar_salida', 'Registrar salidas', 'Registrar salidas de productos'),
        ('registrar_transferencia', 'Registrar transferencias', 'Transferir entre bodegas'),
        ('registrar_merma', 'Registrar mermas', 'Registrar productos perdidos o dañados'),
    ]),
    ('reportes', [
        ('ver_reportes', 'Ver reportes', 'Acceder a reportes del sistema'),
        ('exportar_reportes', 'Exportar reportes', 'Exportar reportes a otros formatos'),
    ]),
    ('alertas', [
        ('ver_alertas', 'Ver alertas', 'Consultar alertas del sistema'),
        ('configurar_alertas', 'Configurar alertas', 'Configurar stock mínimo y alertas'),
    ]),
    ('auditoria', [
        ('ver_auditoria', 'Ver auditoría', 'Consultar registros de auditoría del sistema'),
    ]),
]

# === ROLES DEL SISTEMA ===
# Cada rol tiene un conjunto específico de permisos
ROLES = {
    'administrador': {
        'nombre': 'Administrador',
        'descripcion': 'Acceso completo al sistema. Puede gestionar usuarios, '
                       'roles, productos, bodegas y ver todos los reportes.',
        'permisos': '*',  # Todos los permisos
    },
    'encargado_bodega': {
        'nombre': 'Encargado de bodega',
        'descripcion': 'Gestiona el inventario de las bodegas asignadas. '
                       'Registra movimientos y consulta stock.',
        'permisos': [
            'ver_usuario',
            'ver_producto', 'crear_producto', 'editar_producto',
            'ver_bodega', 'editar_bodega',
            'ver_movimiento', 'registrar_entrada', 'registrar_salida',
            'registrar_transferencia', 'registrar_merma',
            'ver_reportes',
            'ver_alertas', 'configurar_alertas',
        ],
    },
    'operador': {
        'nombre': 'Operador',
        'descripcion': 'Registra entradas y salidas de inventario. '
                       'Consulta productos y stock.',
        'permisos': [
            'ver_producto',
            'ver_bodega',
            'ver_movimiento', 'registrar_entrada', 'registrar_salida',
            'ver_alertas',
        ],
    },
}


class Command(BaseCommand):
    help = 'Puebla la base de datos con datos iniciales del sistema'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Elimina los datos existentes antes de crear',
        )
        parser.add_argument(
            '--sin-admin',
            action='store_true',
            help='No crea el superusuario de prueba',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('=== SEEDING SMARTSTOCK ==='))

        if options['reset']:
            self._reset_datos()

        self._crear_permisos()
        self._crear_roles()

        if not options['sin_admin']:
            self._crear_admin_prueba()

        self.stdout.write(self.style.SUCCESS('\n✓ Seeding completado exitosamente.\n'))

    def _reset_datos(self):
        self.stdout.write('Eliminando datos existentes...')
        Usuario.objects.filter(is_superuser=False).delete()
        Rol.objects.all().delete()
        Permiso.objects.all().delete()
        self.stdout.write(self.style.WARNING('  Datos anteriores eliminados.'))

    def _crear_permisos(self):
        self.stdout.write('\n→ Creando permisos...')
        creados = 0
        for modulo, permisos in PERMISOS_CATALOGO:
            for codigo, nombre, descripcion in permisos:
                _, created = Permiso.objects.get_or_create(
                    codigo=codigo,
                    defaults={
                        'nombre': nombre,
                        'descripcion': descripcion,
                        'modulo': modulo,
                    }
                )
                if created:
                    creados += 1
                    self.stdout.write(f'  ✓ {codigo}')
        self.stdout.write(self.style.SUCCESS(f'  Total: {creados} permisos creados.'))

    def _crear_roles(self):
        self.stdout.write('\n→ Creando roles del sistema...')

        for codigo, config in ROLES.items():
            rol, created = Rol.objects.get_or_create(
                codigo=codigo,
                defaults={
                    'nombre': config['nombre'],
                    'descripcion': config['descripcion'],
                    'es_sistema': True,
                }
            )

            # Asignar permisos
            if config['permisos'] == '*':
                permisos = Permiso.objects.all()
            else:
                permisos = Permiso.objects.filter(codigo__in=config['permisos'])

            rol.permisos.set(permisos)

            status = 'creado' if created else 'actualizado'
            self.stdout.write(
                f'  ✓ {config["nombre"]} ({status}) - {permisos.count()} permisos'
            )

    def _crear_admin_prueba(self):
        self.stdout.write('\n→ Creando superusuario de prueba...')

        email_admin = 'admin@smartstock.cl'
        password_admin = 'Admin1234!'

        if Usuario.objects.filter(email=email_admin).exists():
            self.stdout.write(self.style.WARNING(
                f'  El usuario {email_admin} ya existe. No se crea nuevamente.'
            ))
            return

        rol_admin = Rol.objects.get(codigo='administrador')

        Usuario.objects.create_superuser(
            email=email_admin,
            password=password_admin,
            nombres='Administrador',
            apellidos='SmartStock',
            rol=rol_admin,
        )

        self.stdout.write(self.style.SUCCESS(
            f'  ✓ Superusuario creado.\n'
            f'    Email:    {email_admin}\n'
            f'    Password: {password_admin}\n'
            f'    ⚠️  Cambia esta contraseña en producción.'
        ))
