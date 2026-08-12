from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("clinic", "0019_encounter_operational_timing")]

    operations = [
        migrations.AddField(
            model_name="spirometryresult",
            name="dx_epoc",
            field=models.BooleanField(default=False, verbose_name="DX: EPOC"),
        ),
        migrations.AlterField(
            model_name="encounter",
            name="bronchodilator_wait_minutes",
            field=models.PositiveSmallIntegerField(default=10, verbose_name="Espera de broncodilatador"),
        ),
    ]
