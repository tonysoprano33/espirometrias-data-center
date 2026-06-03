from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0002_default_referring_physician"),
    ]

    operations = [
        migrations.AlterField(
            model_name="walktest",
            name="borg_final",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="Borg final"),
        ),
        migrations.AlterField(
            model_name="walktest",
            name="completed",
            field=models.BooleanField(default=True, verbose_name="Prueba concluida"),
        ),
        migrations.AlterField(
            model_name="walktest",
            name="distance_meters",
            field=models.PositiveSmallIntegerField(
                choices=[(100, "100"), (200, "200")],
                default=200,
                verbose_name="Distancia",
            ),
        ),
    ]
