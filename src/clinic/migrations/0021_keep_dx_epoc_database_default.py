from django.db import migrations


def keep_dx_epoc_default(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "ALTER TABLE clinic_spirometryresult "
            "ALTER COLUMN dx_epoc SET DEFAULT FALSE"
        )


def remove_dx_epoc_default(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "ALTER TABLE clinic_spirometryresult "
            "ALTER COLUMN dx_epoc DROP DEFAULT"
        )


class Migration(migrations.Migration):
    dependencies = [("clinic", "0020_spirometryresult_dx_epoc_and_bronco_default")]

    operations = [
        migrations.RunPython(keep_dx_epoc_default, remove_dx_epoc_default),
    ]
