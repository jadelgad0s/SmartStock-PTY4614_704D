"""Guardia conservadora para eliminación física de registros del inventario.

La desactivación es la acción recomendada para entidades con historial.
"""
def tiene_relaciones(objeto, ignorar=()):
    """No borrar si hay referencias, salvo hijos sin historial explícitamente permitidos."""
    for relacion in objeto._meta.related_objects:
        if relacion.get_accessor_name() in ignorar:
            continue
        campo = relacion.field
        if relacion.related_model._base_manager.filter(**{campo.name: objeto}).exists():
            return True
    return False
