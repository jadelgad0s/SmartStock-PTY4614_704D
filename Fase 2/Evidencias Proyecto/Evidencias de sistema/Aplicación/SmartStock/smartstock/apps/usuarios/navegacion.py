"""Destinos y módulos disponibles para la cuenta autenticada."""

DASHBOARD = '/dashboard/'
INICIO_BODEGA = '/inicio-bodega/'
MOVIMIENTOS = '/movimientos/'
CATALOGO = '/productos/'


def cuenta_habilitada(usuario):
    return bool(usuario and usuario.is_authenticated and usuario.activo and (
        usuario.is_superuser or bool(usuario.rol_id and usuario.rol.activo)
    ))


def es_administrador(usuario):
    return cuenta_habilitada(usuario) and usuario.cuenta_protegida


def puede_acceder_admin(usuario):
    return es_administrador(usuario) and usuario.is_staff


def puede_supervisar_bodega(usuario):
    return cuenta_habilitada(usuario) and (
        usuario.is_superuser or usuario.rol.codigo in ('administrador', 'encargado_bodega')
    )


def puede_transferir(usuario):
    return cuenta_habilitada(usuario) and usuario.tiene_permiso('registrar_transferencia')


def inicio_usuario(usuario, modulos=None):
    if modulos is None:
        modulos = modulos_usuario(usuario)
    if DASHBOARD in modulos:
        return DASHBOARD
    if INICIO_BODEGA in modulos:
        return INICIO_BODEGA
    if MOVIMIENTOS in modulos and usuario.rol_id and usuario.rol.codigo == 'operador':
        return MOVIMIENTOS
    if CATALOGO in modulos:
        return CATALOGO
    return next(iter(modulos), '/')


def modulos_usuario(usuario):
    if not cuenta_habilitada(usuario):
        return []
    admin = es_administrador(usuario)
    permisos = set(usuario.rol.permisos.values_list('codigo', flat=True)) if usuario.rol_id else set()
    rutas = [
        ruta for permiso, ruta in (
            ('ver_producto', CATALOGO), ('ver_movimiento', MOVIMIENTOS), ('ver_bodega', '/bodegas/'),
            ('ver_bodega', '/ubicaciones/'), ('registrar_transferencia', '/transferencias/'),
            ('registrar_merma', '/mermas/'), ('ver_reportes', '/reportes/'),
        )
        if usuario.is_superuser or permiso in permisos or admin and permiso in (
            'ver_producto', 'ver_movimiento', 'ver_bodega',
        )
    ]
    if puede_supervisar_bodega(usuario):
        rutas.append(INICIO_BODEGA)
    if admin:
        rutas.extend([DASHBOARD, '/auditoria/', '/usuarios/', '/alertas-sms/'])
    if puede_acceder_admin(usuario):
        rutas.append('/admin/')
    return rutas
