from django.apps import AppConfig


class ClinicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "clinic"
    verbose_name = "Clinica respiratoria"

    def ready(self):
        from . import signals  # noqa: F401
