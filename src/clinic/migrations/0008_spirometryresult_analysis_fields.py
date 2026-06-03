from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0007_alter_encounter_status_encounterevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="spirometryresult",
            name="extracted_source",
            field=models.CharField(blank=True, max_length=40, verbose_name="Fuente de extraccion"),
        ),
        migrations.AddField(
            model_name="spirometryresult",
            name="measured_values",
            field=models.JSONField(blank=True, default=dict, verbose_name="Valores extraidos"),
        ),
        migrations.AddField(
            model_name="spirometryresult",
            name="suggested_code",
            field=models.CharField(blank=True, max_length=24, verbose_name="Codigo sugerido"),
        ),
        migrations.AddField(
            model_name="spirometryresult",
            name="suggested_probability",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Probabilidad sugerida"),
        ),
        migrations.AddField(
            model_name="spirometryresult",
            name="suggested_summary",
            field=models.TextField(blank=True, verbose_name="Resumen sugerido"),
        ),
    ]
