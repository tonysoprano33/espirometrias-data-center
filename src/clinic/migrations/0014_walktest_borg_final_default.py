from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0013_default_clinical_roles"),
    ]

    operations = [
        migrations.AlterField(
            model_name="walktest",
            name="borg_final",
            field=models.PositiveSmallIntegerField(default=1, verbose_name="Borg final"),
        ),
    ]
