from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0015_encounter_technician_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="encounter",
            name="medical_control_today",
            field=models.BooleanField(default=False, verbose_name="Control medico hoy"),
        ),
    ]
