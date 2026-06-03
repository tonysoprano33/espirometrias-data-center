from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0003_walktest_defaults"),
    ]

    operations = [
        migrations.AlterField(
            model_name="patient",
            name="dni",
            field=models.CharField(blank=True, max_length=20, null=True, unique=True, verbose_name="DNI"),
        ),
    ]
