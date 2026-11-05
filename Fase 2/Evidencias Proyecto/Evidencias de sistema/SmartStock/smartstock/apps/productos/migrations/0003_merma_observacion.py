from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('productos', '0002_alerta_bodega_detallemovimiento_detalletransferencia_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='merma',
            name='observacion',
            field=models.TextField(blank=True, default=''),
        ),
    ]
