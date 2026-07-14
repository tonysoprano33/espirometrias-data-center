import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0011_encounter_deleted_at_encounter_deleted_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="deletion_batch",
            field=models.UUIDField(blank=True, db_index=True, null=True, verbose_name="Lote de eliminacion"),
        ),
        migrations.AddField(
            model_name="encounter",
            name="deletion_batch",
            field=models.UUIDField(blank=True, db_index=True, null=True, verbose_name="Lote de eliminacion"),
        ),
        migrations.AddField(
            model_name="walktest",
            name="minute_readings",
            field=models.JSONField(blank=True, default=list, verbose_name="Mediciones reales por minuto"),
        ),
        migrations.AddField(
            model_name="spirometryresult",
            name="suggested_bronchodilator_positive",
            field=models.BooleanField(blank=True, null=True, verbose_name="Broncodilatador positivo sugerido"),
        ),
        migrations.AddField(
            model_name="spirometryresult",
            name="suggested_bronchodilator_reason",
            field=models.TextField(blank=True, verbose_name="Motivo de sugerencia broncodilatadora"),
        ),
        migrations.AddField(
            model_name="generatedreport",
            name="content_sha256",
            field=models.CharField(blank=True, db_index=True, max_length=64, verbose_name="SHA-256"),
        ),
        migrations.AddField(
            model_name="generatedreport",
            name="source_snapshot",
            field=models.JSONField(blank=True, default=dict, verbose_name="Datos fuente"),
        ),
        migrations.AddField(
            model_name="generatedreport",
            name="supersedes",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="superseded_by", to="clinic.generatedreport", verbose_name="Reemplaza a"),
        ),
        migrations.AlterModelOptions(
            name="encounter",
            options={
                "ordering": ["-encounter_date", "-encounter_time", "-created_at"],
                "permissions": [
                    ("manage_agenda", "Puede gestionar la agenda clinica"),
                    ("review_medically", "Puede realizar revisiones medicas"),
                    ("purge_clinical_data", "Puede eliminar datos clinicos definitivamente"),
                    ("view_clinical_statistics", "Puede ver estadisticas clinicas"),
                ],
                "verbose_name": "Atencion",
                "verbose_name_plural": "Atenciones",
            },
        ),
    ]
