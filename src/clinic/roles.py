from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission


WORK_MODES = {"secretaria", "medico", "espirometrista"}

# Estas cuentas representan puestos de trabajo, no una preferencia del navegador.
ROLE_SESSION_USERS = {
    "secretaria": "secretaria",
    "medico": "medico",
    "espirometro": "espirometrista",
}

ROLE_SESSION_LABELS = {
    "secretaria": "Secretaría",
    "medico": "Médico",
    "espirometrista": "Espirometro",
}

ROLE_PERMISSION_CODENAMES = {
    "secretaria": {"manage_agenda"},
    "medico": {"review_medically"},
    "espirometrista": {
        "manage_agenda",
        "review_medically",
        "view_clinical_statistics",
        "purge_clinical_data",
    },
}


def fixed_work_mode_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    username = str(getattr(user, "username", "") or "").strip().lower()
    return ROLE_SESSION_USERS.get(username)


def get_request_work_mode(request):
    fixed_mode = fixed_work_mode_for_user(request.user)
    if fixed_mode:
        return fixed_mode

    saved_mode = str(request.session.get("clinic_work_mode", "") or "").strip()
    return saved_mode if saved_mode in WORK_MODES else "espirometrista"


def work_mode_label(mode):
    return ROLE_SESSION_LABELS.get(mode, ROLE_SESSION_LABELS["espirometrista"])


def provision_role_session_accounts():
    """Create the three reserved work-station accounts without touching other users."""
    password = str(getattr(settings, "ROLE_SESSION_PASSWORD", "") or "").strip()
    if not password:
        return

    User = get_user_model()
    all_clinic_permissions = Permission.objects.filter(content_type__app_label="clinic")
    permissions_by_codename = {
        permission.codename: permission for permission in all_clinic_permissions
    }

    for username, mode in ROLE_SESSION_USERS.items():
        user, _ = User.objects.get_or_create(username=username)
        changed_fields = []
        if not user.is_active:
            user.is_active = True
            changed_fields.append("is_active")
        if user.is_staff:
            user.is_staff = False
            changed_fields.append("is_staff")
        if user.is_superuser:
            user.is_superuser = False
            changed_fields.append("is_superuser")
        if not user.check_password(password):
            user.set_password(password)
            changed_fields.append("password")
        if changed_fields:
            user.save(update_fields=changed_fields)

        if mode == "espirometrista":
            expected_permissions = list(all_clinic_permissions)
        else:
            expected_permissions = [
                permissions_by_codename[codename]
                for codename in ROLE_PERMISSION_CODENAMES[mode]
                if codename in permissions_by_codename
            ]
        current_permission_ids = set(user.user_permissions.values_list("pk", flat=True))
        expected_permission_ids = {permission.pk for permission in expected_permissions}
        if current_permission_ids != expected_permission_ids:
            user.user_permissions.set(expected_permissions)
        if user.groups.exists():
            user.groups.clear()
