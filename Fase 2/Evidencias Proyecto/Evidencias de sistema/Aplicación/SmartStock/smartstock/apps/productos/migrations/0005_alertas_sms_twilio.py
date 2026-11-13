# Alertas SMS: cola persistente, ciclos por bodega y cuota diaria compartida.

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0004_notificacion'),
    ]

    operations = [
        migrations.CreateModel(
            name='LimiteDiarioSMS',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField(unique=True)),
                ('intentos', models.PositiveIntegerField(default=0)),
            ],
            options={
                'db_table': 'limite_diario_sms',
            },
        ),
        migrations.CreateModel(
            name='EnvioAlertaSMS',
            fields=[
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_modificacion', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ciclo', models.UUIDField()),
                ('nivel', models.PositiveSmallIntegerField()),
                ('sku', models.CharField(max_length=50)),
                ('producto_nombre', models.CharField(max_length=200)),
                ('bodega_nombre', models.CharField(max_length=100)),
                ('cantidad', models.IntegerField()),
                ('minimo', models.IntegerField()),
                ('destinatario', models.CharField(max_length=16)),
                ('mensaje', models.CharField(max_length=160)),
                ('estado', models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('ENVIANDO', 'Envío en curso'), ('ACEPTADO', 'Aceptado por Twilio'), ('ENVIADO', 'Enviado a la red'), ('ENTREGADO', 'Entregado'), ('NO_ENTREGADO', 'No entregado'), ('RECHAZADO', 'Rechazado'), ('INCIERTO', 'Resultado por confirmar'), ('CANCELADO', 'Cancelado')], db_index=True, default='PENDIENTE', max_length=20)),
                ('intentos', models.PositiveSmallIntegerField(default=0)),
                ('ultimo_intento', models.DateTimeField(blank=True, null=True)),
                ('proximo_intento', models.DateTimeField(blank=True, null=True)),
                ('twilio_sid', models.CharField(blank=True, max_length=34, null=True, unique=True)),
                ('codigo_error', models.CharField(blank=True, max_length=12)),
                ('detalle', models.CharField(blank=True, max_length=200)),
                ('bodega', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='productos.bodega')),
                ('producto', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='productos.producto')),
            ],
            options={
                'verbose_name': 'envío de alerta SMS',
                'verbose_name_plural': 'envíos de alertas SMS',
                'db_table': 'envios_alertas_sms',
                'ordering': ['-fecha_creacion', '-id'],
                'constraints': [models.UniqueConstraint(fields=('ciclo', 'nivel', 'destinatario'), name='sms_un_envio_por_nivel_ciclo')],
            },
        ),
        migrations.CreateModel(
            name='EstadoStockSMS',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_modificacion', models.DateTimeField(auto_now=True)),
                ('ciclo', models.UUIDField(default=uuid.uuid4)),
                ('nivel_maximo', models.PositiveSmallIntegerField(default=0)),
                ('bodega', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='productos.bodega')),
                ('producto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='productos.producto')),
            ],
            options={
                'db_table': 'estado_stock_sms',
                'constraints': [models.UniqueConstraint(fields=('producto', 'bodega'), name='sms_estado_producto_bodega')],
            },
        ),
    ]
