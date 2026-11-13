"""Crear notificaciones después de la migración de mermas en producción."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('productos', '0003_merma_observacion'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='Notificacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_modificacion', models.DateTimeField(auto_now=True)),
                ('tipo', models.CharField(choices=[
                    ('MOVIMIENTO', 'Movimiento de stock'),
                    ('MERMA', 'Merma registrada'),
                    ('STOCK_BAJO', 'Stock bajo'),
                    ('OTRO', 'Otro'),
                ], default='OTRO', max_length=20)),
                ('titulo', models.CharField(max_length=150)),
                ('mensaje', models.TextField()),
                ('link', models.CharField(blank=True, max_length=200)),
                ('leida', models.BooleanField(db_index=True, default=False)),
                ('usuario_destino', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notificaciones',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'db_table': 'notificaciones', 'ordering': ['-fecha_creacion']},
        ),
    ]
