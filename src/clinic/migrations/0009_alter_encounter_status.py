from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0008_spirometryresult_analysis_fields"),
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
                default="Cargada",
                max_length=30,
                verbose_name="Estado",
            ),
        ),
    ]
