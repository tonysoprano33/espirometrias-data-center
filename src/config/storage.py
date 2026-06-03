import json
import mimetypes
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage


class SupabaseStorage(Storage):
    bucket_name = getattr(settings, "SUPABASE_STORAGE_BUCKET", "attachments")
    signed_url_ttl = getattr(settings, "SUPABASE_STORAGE_SIGNED_URL_TTL", 3600)

    def _api_base(self):
        return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1"

    def _auth_headers(self):
        api_key = getattr(settings, "SUPABASE_STORAGE_API_KEY", "")
        return {
            "Authorization": f"Bearer {api_key}",
            "apikey": api_key,
        }

    def _request(self, method, path, *, data=None, json_body=None, headers=None):
        request_headers = self._auth_headers()
        if headers:
            request_headers.update(headers)
        payload = data
        if json_body is not None:
            payload = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        request = Request(f"{self._api_base()}/{path.lstrip('/')}", data=payload, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                return response.read(), response.headers
        except HTTPError as error:
            body = error.read().decode("utf-8", "ignore")
            raise RuntimeError(f"Supabase storage {method} {path} failed ({error.code}): {body}")

    def _ensure_bucket(self):
        try:
            self._request(
                "POST",
                "bucket",
                json_body={"id": self.bucket_name, "name": self.bucket_name, "public": False},
            )
        except RuntimeError as error:
            if "already" not in str(error).lower() and "duplicate" not in str(error).lower():
                raise

    def _object_path(self, name):
        cleaned = str(name).replace("\\", "/")
        return f"{self.bucket_name}/{quote(cleaned, safe='/')}"

    def _open(self, name, mode="rb"):
        body, _ = self._request("GET", f"object/authenticated/{self._object_path(name)}")
        return ContentFile(body, name=name)

    def _save(self, name, content):
        self._ensure_bucket()
        file_bytes = content.read()
        content_type = getattr(content, "content_type", "") or mimetypes.guess_type(str(name))[0] or "application/octet-stream"
        self._request(
            "POST",
            f"object/{self._object_path(name)}",
            data=file_bytes,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
        return str(name).replace("\\", "/")

    def delete(self, name):
        try:
            self._request("DELETE", f"object/{self._object_path(name)}")
        except RuntimeError:
            return

    def exists(self, name):
        try:
            self._request("GET", f"object/info/{self._object_path(name)}")
            return True
        except RuntimeError:
            return False

    def url(self, name):
        body, _ = self._request(
            "POST",
            f"object/sign/{self._object_path(name)}",
            json_body={"expiresIn": self.signed_url_ttl},
        )
        payload = json.loads(body.decode("utf-8"))
        return urljoin(f"{settings.SUPABASE_URL.rstrip('/')}/", payload["signedURL"].lstrip("/"))

    def size(self, name):
        body, _ = self._request("GET", f"object/info/{self._object_path(name)}")
        payload = json.loads(body.decode("utf-8"))
        return int(payload.get("metadata", {}).get("size") or payload.get("size") or 0)

    def path(self, name):
        content = self._open(name)
        suffix = Path(str(name)).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content.read())
            return temp_file.name
