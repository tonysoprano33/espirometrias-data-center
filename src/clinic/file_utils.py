from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile


@contextmanager
def local_field_file_path(field_file):
    """Expose a FieldFile as a local path and always remove remote temp copies."""
    storage = field_file.storage
    try:
        local_path = storage.path(field_file.name)
    except (AttributeError, NotImplementedError):
        local_path = ""

    if local_path and not storage.__class__.__module__.startswith("config.storage"):
        yield Path(local_path)
        return

    suffix = Path(field_file.name or "").suffix or ".bin"
    temporary_path = None
    try:
        with field_file.open("rb") as source, NamedTemporaryFile(delete=False, suffix=suffix) as target:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                target.write(chunk)
            temporary_path = Path(target.name)
        yield temporary_path
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
