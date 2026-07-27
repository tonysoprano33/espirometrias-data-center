# Generated manually to keep the operational timing rollout explicit.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0018_optimize_encounter_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="encounter",
            name="waiting_started_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Comenzo a esperar el"),
        ),
        migrations.AddField(
            model_name="encounter",
            name="first_vitals_recorded_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Primeros signos cargados el"),
        ),
        migrations.AddField(
            model_name="encounter",
            name="discharged_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Finalizo la atencion el"),
        ),
        migrations.AddField(
            model_name="encounter",
            name="bronchodilator_administered_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Broncodilatador aplicado el"),
        ),
        migrations.AddField(
            model_name="encounter",
            name="bronchodilator_wait_minutes",
            field=models.PositiveSmallIntegerField(default=15, verbose_name="Espera de broncodilatador"),
        ),
    ]
