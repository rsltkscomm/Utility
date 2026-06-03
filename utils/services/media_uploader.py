import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


class MediaUploadError(Exception):
    pass


_CIRCUIT_OPEN_UNTIL = 0.0
_CIRCUIT_REASON = ""


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _upload_required():
    return os.getenv("MEDIA_UPLOAD_REQUIRED", "no").lower() == "yes"


class MediaUploader:
    def __init__(self):
        self.base_url = os.getenv("MEDIA_SERVER_URL", "").rstrip("/")
        self.token = os.getenv("MEDIA_SERVER_TOKEN", "")
        self.enabled = os.getenv("MEDIA_UPLOAD_ENABLED", "yes").lower() == "yes"
        self.retries = max(1, _env_int("MEDIA_UPLOAD_RETRIES", 1))
        self.connect_timeout = max(1, _env_int("MEDIA_UPLOAD_CONNECT_TIMEOUT", 1))
        self.read_timeout = max(1, _env_int("MEDIA_UPLOAD_READ_TIMEOUT", _env_int("MEDIA_UPLOAD_TIMEOUT", 2)))
        self.circuit_open_seconds = max(0, _env_int("MEDIA_UPLOAD_CIRCUIT_OPEN_SECONDS", 300))
        self.public_base_url = os.getenv("MEDIA_PUBLIC_BASE_URL", "").rstrip("/")

    def _public_url(self, returned_url):
        if not returned_url or not self.public_base_url:
            return returned_url

        parsed = urlparse(returned_url)
        marker = "/media/"
        if marker not in parsed.path:
            return returned_url

        media_path = parsed.path.split(marker, 1)[1]
        return f"{self.public_base_url}/{media_path}"

    def upload(self, file_path, test_name, file_type, run_id="", worker_id=""):
        global _CIRCUIT_OPEN_UNTIL, _CIRCUIT_REASON

        path = Path(file_path)
        if not self.enabled or not self.base_url or not path.exists():
            return None

        now = time.monotonic()
        if not _upload_required() and now < _CIRCUIT_OPEN_UNTIL:
            print(f"\n[MEDIA] Server unavailable; using local {file_type}: {_CIRCUIT_REASON}")
            return None

        last_error = None

        for attempt in range(1, self.retries + 1):
            try:
                with open(path, "rb") as file_obj:
                    response = requests.post(
                        f"{self.base_url}/upload",
                        headers={"Authorization": f"Bearer {self.token}"},
                        data={
                            "test_name": test_name,
                            "file_type": file_type,
                            "run_id": run_id,
                            "worker_id": worker_id,
                        },
                        files={"file": (path.name, file_obj)},
                        timeout=(self.connect_timeout, self.read_timeout),
                    )

                response.raise_for_status()
                _CIRCUIT_OPEN_UNTIL = 0.0
                _CIRCUIT_REASON = ""
                return self._public_url(response.json().get("file_url"))
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(0.25 * attempt, 1))

        if not _upload_required() and self.circuit_open_seconds:
            _CIRCUIT_OPEN_UNTIL = time.monotonic() + self.circuit_open_seconds
            _CIRCUIT_REASON = str(last_error)
            print(f"\n[MEDIA] Upload server unavailable; falling back to local media for {self.circuit_open_seconds}s")
            return None

        raise MediaUploadError(f"Upload failed for {file_path}: {last_error}")