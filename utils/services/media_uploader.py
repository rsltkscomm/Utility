import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


class MediaUploadError(Exception):
    pass


DEFAULT_SERVER_URL = "http://172.31.1.69:8000"
DEFAULT_PUBLIC_URL = "http://172.31.1.69:8000/media"

_CIRCUIT_OPEN_UNTIL = 0.0
_CIRCUIT_REASON = ""
_CONSECUTIVE_FAILURES = 0
_CONFIG_LOGGED = False


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _upload_required():
    return os.getenv("MEDIA_UPLOAD_REQUIRED", "no").lower() == "yes"


class MediaUploader:
    def __init__(self):
        global _CONFIG_LOGGED

        self.base_url = os.getenv("MEDIA_SERVER_URL", DEFAULT_SERVER_URL).rstrip("/")
        self.token = os.getenv("MEDIA_SERVER_TOKEN", "")
        self.enabled = os.getenv("MEDIA_UPLOAD_ENABLED", "yes").lower() == "yes"
        self.retries = max(1, _env_int("MEDIA_UPLOAD_RETRIES", 3))
        self.connect_timeout = max(1, _env_int("MEDIA_UPLOAD_CONNECT_TIMEOUT", 5))
        self.read_timeout = max(
            1, _env_int("MEDIA_UPLOAD_READ_TIMEOUT", _env_int("MEDIA_UPLOAD_TIMEOUT", 30))
        )
        self.circuit_open_seconds = max(0, _env_int("MEDIA_UPLOAD_CIRCUIT_OPEN_SECONDS", 30))
        self.failure_threshold = max(1, _env_int("MEDIA_UPLOAD_FAILURE_THRESHOLD", 5))
        self.public_base_url = os.getenv("MEDIA_PUBLIC_BASE_URL", DEFAULT_PUBLIC_URL).rstrip("/")

        if not _CONFIG_LOGGED:
            _CONFIG_LOGGED = True
            print(
                f"\n[MEDIA] Config -> server={self.base_url} | public={self.public_base_url} | "
                f"enabled={self.enabled} | token_set={'yes' if self.token else 'NO'}"
            )
            if not self.token:
                print("[MEDIA] WARNING: MEDIA_SERVER_TOKEN is not set; uploads will be rejected (401)")

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
        global _CIRCUIT_OPEN_UNTIL, _CIRCUIT_REASON, _CONSECUTIVE_FAILURES

        path = Path(file_path)

        if not self.enabled:
            print(f"\n[MEDIA] Skipped {path.name}: MEDIA_UPLOAD_ENABLED is not 'yes'")
            return None
        if not self.base_url:
            print(f"\n[MEDIA] Skipped {path.name}: MEDIA_SERVER_URL is empty")
            return None
        if not path.exists():
            print(f"\n[MEDIA] Skipped: file not found {path}")
            return None

        if not _upload_required() and time.monotonic() < _CIRCUIT_OPEN_UNTIL:
            print(f"\n[MEDIA] Circuit open; local {file_type} used for {path.name}: {_CIRCUIT_REASON}")
            return None

        last_error = None
        retryable = True

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

                if response.status_code in (401, 403, 422):
                    # Wrong token / bad request: retrying will not help
                    retryable = False
                    raise MediaUploadError(f"HTTP {response.status_code}: {response.text[:200]}")

                response.raise_for_status()

                file_url = response.json().get("file_url")
                if not file_url:
                    raise MediaUploadError(f"No file_url in response: {response.text[:200]}")

                _CONSECUTIVE_FAILURES = 0
                _CIRCUIT_OPEN_UNTIL = 0.0
                _CIRCUIT_REASON = ""
                return self._public_url(file_url)

            except Exception as exc:
                last_error = exc
                print(f"\n[MEDIA] Attempt {attempt}/{self.retries} failed for {path.name}: {exc}")
                if not retryable:
                    break
                if attempt < self.retries:
                    time.sleep(min(0.5 * attempt, 2))

        _CONSECUTIVE_FAILURES += 1

        if _upload_required():
            raise MediaUploadError(f"Upload failed for {file_path}: {last_error}")

        if self.circuit_open_seconds and _CONSECUTIVE_FAILURES >= self.failure_threshold:
            _CIRCUIT_OPEN_UNTIL = time.monotonic() + self.circuit_open_seconds
            _CIRCUIT_REASON = str(last_error)
            print(
                f"\n[MEDIA] {_CONSECUTIVE_FAILURES} consecutive failures; "
                f"using local media for {self.circuit_open_seconds}s"
            )

        print(f"\n[MEDIA] Falling back to local file for {path.name}: {last_error}")
        return None