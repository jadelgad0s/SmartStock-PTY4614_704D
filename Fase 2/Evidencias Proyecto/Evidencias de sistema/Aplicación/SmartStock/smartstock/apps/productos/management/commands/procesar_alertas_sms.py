from django.core.management.base import BaseCommand, CommandError

from apps.productos.alertas_sms import configuracion_sms, procesar_pendientes_sms


class Command(BaseCommand):
    help = 'Procesa hasta 3 SMS pendientes; puede generar cargos de Twilio. No reenvía resultados inciertos.'

    def handle(self, *args, **options):
        configuracion = configuracion_sms()
        if not configuracion['activa'] or not configuracion['lista']:
            raise CommandError('SMS desactivados o configuración incompleta. Consulta /api/v1/alertas-sms/estado/.')
        revisados = procesar_pendientes_sms()
        self.stdout.write(f'Pendientes revisados: {revisados}. Consulta el historial para conocer el resultado.')
