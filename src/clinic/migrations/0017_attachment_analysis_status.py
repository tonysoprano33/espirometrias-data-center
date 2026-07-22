from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0016_encounter_medical_control_today"),
    ]

    operations = [
        migrations.AddField(
            model_name="attachment",
            name="analysis_attempted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Ultimo intento de lectura"),
        ),
        migrations.AddField(
            model_name="attachment",
            name="analysis_error",
            field=models.CharField(blank=True, max_length=280, verbose_name="Detalle de lectura"),
        ),
        migrations.AddField(
            model_name="attachment",
            name="analysis_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("uploaded", "Archivo subido"),
                    ("detected", "Datos detectados"),
                    ("failed", "Falló la lectura"),
                ],
                default="",
                max_length=20,
                verbose_name="Estado de lectura",
            ),
        ),
    ]
