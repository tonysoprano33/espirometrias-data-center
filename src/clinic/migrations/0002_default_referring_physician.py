from django.db import migrations


def create_default_physician(apps, schema_editor):
    ReferringPhysician = apps.get_model("clinic", "ReferringPhysician")
    ReferringPhysician.objects.get_or_create(
        full_name="DR. GUSTAVO PIGUILLEM",
        defaults={"is_default": True, "active": True},
    )


def remove_default_physician(apps, schema_editor):
    ReferringPhysician = apps.get_model("clinic", "ReferringPhysician")
    ReferringPhysician.objects.filter(full_name="DR. GUSTAVO PIGUILLEM").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_physician, remove_default_physician),
    ]
