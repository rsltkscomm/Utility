import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from utils.ini_file_reader.config_reader import ConfigReader


class MediaUploadError(Exception):
    pass


_CIRCUIT_OPEN_UNTIL = 0.0
_CIRCUIT_REASON = ""


def _env_int(name, default):
    try:
        val = ConfigReader.get_property(name) or os.getenv(name, str(default))
        return int(val)
    except (TypeError, ValueError):
        return default


def _upload_required():
    val = ConfigReader.get_property("MEDIA_UPLOAD_REQUIRED") or os.getenv("MEDIA_UPLOAD_REQUIRED", "no")
    return str(val).lower() == "yes"


class MediaUploader:
    def __init__(self):
        self._refresh_config()

    def _refresh_config(self):
        self.base_url = (ConfigReader.get_property("MEDIA_SERVER_URL", "") or os.getenv("MEDIA_SERVER_URL", "")).rstrip("/")
        self.token = ConfigReader.get_property("MEDIA_SERVER_TOKEN", "") or os.getenv("MEDIA_SERVER_TOKEN", "")
        self.enabled = (ConfigReader.get_property("MEDIA_UPLOAD_ENABLED") or os.getenv("MEDIA_UPLOAD_ENABLED", "yes")).lower() == "yes"
        self.retries = max(1, _env_int("MEDIA_UPLOAD_RETRIES", 3))
        self.connect_timeout = max(5, _env_int("MEDIA_UPLOAD_CONNECT_TIMEOUT", 15))
        self.read_timeout = max(30, _env_int("MEDIA_UPLOAD_READ_TIMEOUT", _env_int("MEDIA_UPLOAD_TIMEOUT", 180)))
        self.circuit_open_seconds = max(0, _env_int("MEDIA_UPLOAD_CIRCUIT_OPEN_SECONDS", 60))
        self.public_base_url = (ConfigReader.get_property("MEDIA_PUBLIC_BASE_URL", "") or os.getenv("MEDIA_PUBLIC_BASE_URL", "")).rstrip("/")

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

        self._refresh_config()

        path = Path(file_path)
        if not self.enabled:
            return None

        if not self.base_url:
            print(f"\n[MEDIA] Upload skipped: MEDIA_SERVER_URL is not configured for {file_type} ({path.name})")
            return None

        if not path.exists():
            print(f"\n[MEDIA] Upload skipped: File does not exist ({file_path})")
            return None

        now = time.monotonic()
        if not _upload_required() and now < _CIRCUIT_OPEN_UNTIL:
            remaining = int(_CIRCUIT_OPEN_UNTIL - now)
            print(f"\n[MEDIA] Server temporarily bypassed ({remaining}s remaining); using local {file_type}: {_CIRCUIT_REASON}")
            return None

        last_error = None
        try:
            file_size_mb = path.stat().st_size / (1024 * 1024)
        except Exception:
            file_size_mb = 0.0

        for attempt in range(1, self.retries + 1):
            try:
                print(f"\n[MEDIA] Uploading {file_type} ({path.name}, {file_size_mb:.2f} MB) to {self.base_url}/upload (attempt {attempt}/{self.retries}, connect_timeout={self.connect_timeout}s, read_timeout={self.read_timeout}s)...")
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
                public_url = self._public_url(response.json().get("file_url"))
                print(f"\n[MEDIA] Upload successful: {public_url}")
                return public_url
            except Exception as exc:
                last_error = exc
                print(f"\n[MEDIA] Upload attempt {attempt}/{self.retries} failed for {file_type} ({path.name}): {type(exc).__name__}: {exc}")
                if attempt < self.retries:
                    sleep_time = min(2 * attempt, 10)
                    time.sleep(sleep_time)

        if not _upload_required() and self.circuit_open_seconds:
            _CIRCUIT_OPEN_UNTIL = time.monotonic() + self.circuit_open_seconds
            _CIRCUIT_REASON = f"{type(last_error).__name__}: {last_error}"
            print(f"\n[MEDIA] Upload server failed for {self.base_url}/upload: {last_error}. Falling back to local media for {self.circuit_open_seconds}s")
            return None

        raise MediaUploadError(f"Upload failed for {file_path} to {self.base_url}/upload: {last_error}")