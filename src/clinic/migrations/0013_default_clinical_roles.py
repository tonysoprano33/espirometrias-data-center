from django.db import migrations


ROLE_PERMISSIONS = {
    "Secretaria": {
        "manage_agenda",
        "add_patient",
        "change_patient",
        "view_patient",
        "add_encounter",
        "change_encounter",
        "view_encounter",
        "add_vitalsigns",
        "change_vitalsigns",
        "view_vitalsigns",
        "add_walktest",
        "change_walktest",
        "view_walktest",
        "add_attachment",
        "view_attachment",
        "add_referringphysician",
        "change_referringphysician",
        "view_referringphysician",
    },
    "Medicos": {
        "review_medically",
        "view_clinical_statistics",
        "view_patient",
        "change_patient",
        "view_encounter",
        "change_encounter",
        "view_vitalsigns",
        "view_walktest",
        "view_attachment",
        "view_spirometryresult",
        "change_spirometryresult",
        "view_generatedreport",
        "view_encounterevent",
    },
}


def create_default_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    for model in apps.get_app_config("clinic").get_models():
        ContentType.objects.get_or_create(app_label="clinic", model=model._meta.model_name)

    encounter_type = ContentType.objects.get(app_label="clinic", model="encounter")
    custom_permissions = {
        "manage_agenda": "Puede administrar la agenda clinica",
        "review_medically": "Puede validar revisiones medicas",
        "purge_clinical_data": "Puede eliminar datos clinicos definitivamente",
        "view_clinical_statistics": "Puede ver estadisticas clinicas",
    }
    for codename, name in custom_permissions.items():
        Permission.objects.get_or_create(
            content_type=encounter_type,
            codename=codename,
            defaults={"name": name},
        )

    for content_type in ContentType.objects.filter(app_label="clinic"):
        model_label = content_type.model.replace("_", " ")
        for action in ("add", "change", "delete", "view"):
            Permission.objects.get_or_create(
                content_type=content_type,
                codename=f"{action}_{content_type.model}",
                defaults={"name": f"Can {action} {model_label}"},
            )

    clinic_permissions = Permission.objects.filter(content_type__app_label="clinic")
    for role_name, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role_name)
        group.permissions.set(clinic_permissions.filter(codename__in=codenames))

    admin_group, _ = Group.objects.get_or_create(name="Administradores")
    admin_group.permissions.set(clinic_permissions)


def remove_default_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=["Secretaria", "Medicos", "Administradores"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0012_clinical_integrity_and_traceability"),
    ]

    operations = [
        migrations.RunPython(create_default_roles, remove_default_roles),
    ]
