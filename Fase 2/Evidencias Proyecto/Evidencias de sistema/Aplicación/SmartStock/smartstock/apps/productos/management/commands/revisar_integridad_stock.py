"""Diagnóstico de solo lectura, ejecutable antes y después de la migración 0007."""
from importlib import import_module

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = 'Revisa duplicados y cantidades inválidas sin cambiar el inventario.'

    def add_arguments(self, parser):
        parser.add_argument('--database', default='default', choices=tuple(connections))

    def handle(self, *args, **options):
        alias = options['database']
        migracion = import_module('apps.productos.migrations.0007_integridad_stock')
        tablas = {apps.get_model('productos', n)._meta.db_table for n, _, _ in migracion.CANTIDADES}
        if not tablas.issubset(connections[alias].introspection.table_names()):
            raise CommandError('Faltan tablas del inventario. En una instalación nueva ejecuta migrate primero.')
        # Usa los mismos criterios congelados que la migración, sin ejecutarla.
        estado = migracion.inspeccionar(apps, alias)
        self.stdout.write(f"Parejas con stock duplicado: {estado['stock_duplicado']}")
        self.stdout.write(f"Parejas con mínimo duplicado: {estado['minimo_duplicado']}")
        for e in estado['invalidos']:
            self.stderr.write(f"{e['modelo']}.{e['campo']}: {e['total']} cantidades inválidas. IDs: {e['ids']}")
        for e in estado['desbordes']:
            self.stderr.write(f"Producto {e['producto_id']}, bodega {e['bodega_id']}: suma de stock {e['total']} fuera del rango permitido.")
        if estado['invalidos'] or estado['desbordes_total']:
            raise CommandError('Hay cantidades que requieren revisión. No se modificaron datos.')
        if estado['stock_duplicado'] or estado['minimo_duplicado']:
            self.stdout.write(self.style.WARNING('La migración sumará el stock duplicado y conservará el mayor mínimo. Haz un respaldo antes de aplicarla.'))
        else:
            self.stdout.write(self.style.SUCCESS('Inventario sin duplicados ni cantidades fuera de rango.'))
