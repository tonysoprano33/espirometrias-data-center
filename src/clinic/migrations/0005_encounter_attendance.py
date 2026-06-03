from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0004_patient_dni_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="encounter",
            name="attended",
            field=models.BooleanField(default=False, verbose_name="Atendido"),
        ),
        migrations.AddField(
            model_name="encounter",
            name="no_show",
            field=models.BooleanField(default=False, verbose_name="No llego"),
        ),
    ]
