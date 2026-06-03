from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("clinic", "0006_patient_pdf_metadata"),
    ]

    operations = [
        migrations.AlterField(
            model_name="encounter",
            name="status",
            field=models.CharField(
                choices=[
                    ("Pendiente", "Pendiente"),
                    ("Cargada", "Cargada"),
                    ("Revisada por medico", "Revisada por medico"),
                    ("Informe generado", "Informe generado"),
                    ("Entregada", "Entregada"),
                    ("No llego", "No llego"),
                ],
                default="Pendiente",
                max_length=30,
                verbose_name="Estado",
            ),
        ),
        migrations.CreateModel(
            name="EncounterEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("created", "Creacion"),
                            ("updated", "Actualizacion"),
                            ("attendance", "Asistencia"),
                            ("review", "Revision medica"),
                            ("report", "Informe"),
                            ("document", "Documento"),
                            ("import", "Importacion"),
                        ],
                        max_length=20,
                        verbose_name="Tipo",
                    ),
                ),
                ("title", models.CharField(max_length=160, verbose_name="Titulo")),
                ("details", models.TextField(blank=True, verbose_name="Detalle")),
                ("metadata", models.JSONField(blank=True, default=dict, verbose_name="Metadata")),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="encounter_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "encounter",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="clinic.encounter",
                    ),
                ),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="clinic.patient",
                    ),
                ),
            ],
            options={
                "verbose_name": "Evento de atencion",
                "verbose_name_plural": "Eventos de atencion",
                "ordering": ["-created_at"],
            },
        ),
    ]
