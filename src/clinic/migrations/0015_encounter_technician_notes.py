from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0014_walktest_borg_final_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="encounter",
            name="technician_notes",
            field=models.TextField(blank=True, verbose_name="Notas del espirometrista"),
        ),
    ]
