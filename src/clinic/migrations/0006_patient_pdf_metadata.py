from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0005_encounter_attendance"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="age_reported",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Edad informada"),
        ),
        migrations.AddField(
            model_name="patient",
            name="bmi",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="BMI"),
        ),
        migrations.AddField(
            model_name="patient",
            name="ethnicity",
            field=models.CharField(blank=True, max_length=120, verbose_name="Grupo etnico"),
        ),
        migrations.AddField(
            model_name="patient",
            name="first_name",
            field=models.CharField(blank=True, max_length=150, verbose_name="Nombre"),
        ),
        migrations.AddField(
            model_name="patient",
            name="gender",
            field=models.CharField(blank=True, max_length=40, verbose_name="Genero"),
        ),
        migrations.AddField(
            model_name="patient",
            name="height_cm",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Altura cm"),
        ),
        migrations.AddField(
            model_name="patient",
            name="last_name",
            field=models.CharField(blank=True, max_length=150, verbose_name="Apellido"),
        ),
        migrations.AddField(
            model_name="patient",
            name="pack_years",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="Paquete anio"),
        ),
        migrations.AddField(
            model_name="patient",
            name="patient_code",
            field=models.CharField(blank=True, db_index=True, max_length=40, verbose_name="Codigo de paciente"),
        ),
        migrations.AddField(
            model_name="patient",
            name="patient_group",
            field=models.CharField(blank=True, max_length=120, verbose_name="Grupo paciente"),
        ),
        migrations.AddField(
            model_name="patient",
            name="smoking_status",
            field=models.CharField(blank=True, max_length=80, verbose_name="Fuma"),
        ),
        migrations.AddField(
            model_name="patient",
            name="weight_kg",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="Peso kg"),
        ),
    ]
