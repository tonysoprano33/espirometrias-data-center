import shutil
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_migrate
from django.dispatch import receiver

from .models import Attachment
from .roles import provision_role_session_accounts


@receiver(post_delete, sender=Attachment)
def delete_attachment_storage_object(sender, instance, **kwargs):
    file_field = getattr(instance, "file", None)
    file_name = str(getattr(file_field, "name", "") or "")
    storage = getattr(file_field, "storage", None)
    attachment_id = instance.pk

    def cleanup():
        if storage and file_name:
            try:
                storage.delete(file_name)
            except Exception:
                pass
        if attachment_id:
            preview_dir = Path(settings.MEDIA_ROOT) / "previews" / f"attachment_{attachment_id}"
            shutil.rmtree(preview_dir, ignore_errors=True)

    transaction.on_commit(cleanup)


@receiver(post_migrate)
def provision_role_sessions_after_migration(sender, **kwargs):
    if sender.label == "clinic":
        provision_role_session_accounts()
