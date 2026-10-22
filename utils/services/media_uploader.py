import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests


class MediaUploadError(Exception):
    pass


CONFIG_FILE_NAME = "media_config.json"
LOG_FILE_NAME = "media_upload.log"

DEFAULTS = {
    "MEDIA_SERVER_URL": "http://172.31.1.69:8000",
    "MEDIA_PUBLIC_BASE_URL": "http://172.31.1.69:8000/media",
    "MEDIA_SERVER_TOKEN": "",
    "MEDIA_UPLOAD_ENABLED": "yes",
    "MEDIA_UPLOAD_REQUIRED": "no",
    "MEDIA_UPLOAD_RETRIES": "3",
    "MEDIA_UPLOAD_CONNECT_TIMEOUT": "5",
    "MEDIA_UPLOAD_READ_TIMEOUT": "30",
    "MEDIA_UPLOAD_CIRCUIT_OPEN_SECONDS": "30",
    "MEDIA_UPLOAD_FAILURE_THRESHOLD": "5",
    "MEDIA_UPLOAD_USE_PROXY": "no",
}

_CIRCUIT_OPEN_UNTIL = 0.0
_CIRCUIT_REASON = ""
_CONSECUTIVE_FAILURES = 0
_CONFIG_LOGGED = False
_FILE_CONFIG = None
_CONFIG_SOURCE = "defaults"


def _log(message):
    """Print AND append to media_upload.log (workers under xdist hide prints)."""
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} [pid {os.getpid()}] {message}"
    print(f"\n[MEDIA] {message}")
    try:
        with open(Path(os.getcwd()) / LOG_FILE_NAME, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _find_config_file():
    """Look for media_config.json next to this file, in the cwd, and in parent folders."""
    candidates = []
    here = Path(__file__).resolve().parent
    candidates.extend([here, *here.parents])
    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])

    seen = set()
    for folder in candidates:
        if folder in seen:
            continue
        seen.add(folder)
        candidate = folder / CONFIG_FILE_NAME
        if candidate.is_file():
            return candidate
    return None


def _load_file_config():
    global _FILE_CONFIG, _CONFIG_SOURCE
    if _FILE_CONFIG is not None:
        return _FILE_CONFIG

    _FILE_CONFIG = {}
    config_path = _find_config_file()
    if config_path:
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                _FILE_CONFIG = {k: str(v) for k, v in json.load(fh).items()}
            _CONFIG_SOURCE = str(config_path)
        except Exception as exc:
            _log(f"Could not read {config_path}: {exc}")
    return _FILE_CONFIG


def _cfg(name):
    """Priority: environment variable > media_config.json > built-in default."""
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    file_value = _load_file_config().get(name)
    if file_value not in (None, ""):
        return file_value
    return DEFAULTS.get(name, "")


def _cfg_int(name, default):
    try:
        return int(_cfg(name))
    except (TypeError, ValueError):
        return default


def _upload_required():
    return _cfg("MEDIA_UPLOAD_REQUIRED").lower() == "yes"


class MediaUploader:
    def __init__(self):
        global _CONFIG_LOGGED

        self.base_url = _cfg("MEDIA_SERVER_URL").rstrip("/")
        self.public_base_url = _cfg("MEDIA_PUBLIC_BASE_URL").rstrip("/")
        self.token = _cfg("MEDIA_SERVER_TOKEN")
        self.enabled = _cfg("MEDIA_UPLOAD_ENABLED").lower() == "yes"
        self.retries = max(1, _cfg_int("MEDIA_UPLOAD_RETRIES", 3))
        self.connect_timeout = max(1, _cfg_int("MEDIA_UPLOAD_CONNECT_TIMEOUT", 5))
        self.read_timeout = max(1, _cfg_int("MEDIA_UPLOAD_READ_TIMEOUT", 30))
        self.circuit_open_seconds = max(0, _cfg_int("MEDIA_UPLOAD_CIRCUIT_OPEN_SECONDS", 30))
        self.failure_threshold = max(1, _cfg_int("MEDIA_UPLOAD_FAILURE_THRESHOLD", 5))

        # Internal server: ignore HTTP_PROXY / HTTPS_PROXY unless explicitly allowed.
        self.session = requests.Session()
        self.session.trust_env = _cfg("MEDIA_UPLOAD_USE_PROXY").lower() == "yes"

        if not _CONFIG_LOGGED:
            _CONFIG_LOGGED = True
            token_hint = f"{self.token[:3]}***({len(self.token)} chars)" if self.token else "NOT SET"
            _log(
                f"Config source={_CONFIG_SOURCE} | server={self.base_url} | "
                f"public={self.public_base_url} | enabled={self.enabled} | "
                f"required={_upload_required()} | token={token_hint}"
            )
            if not self.token or self.token.startswith("PUT-YOUR"):
                _log("WARNING: token is empty or still the placeholder -> server will return 401")

    def _public_url(self, returned_url):
        if not returned_url or not self.public_base_url:
            return returned_url

        parsed = urlparse(returned_url)
        marker = "/media/"
        if marker not in parsed.path:
            return returned_url

        media_path = parsed.path.split(marker, 1)[1]
        return f"{self.public_base_url}/{media_path}"

    def _skip(self, message):
        _log(message)
        if _upload_required():
            raise MediaUploadError(message)
        return None

    def upload(self, file_path, test_name, file_type, run_id="", worker_id=""):
        global _CIRCUIT_OPEN_UNTIL, _CIRCUIT_REASON, _CONSECUTIVE_FAILURES

        path = Path(file_path)

        if not self.enabled:
            return self._skip(f"Skipped {path.name}: MEDIA_UPLOAD_ENABLED is not 'yes'")
        if not self.base_url:
            return self._skip(f"Skipped {path.name}: MEDIA_SERVER_URL is empty")
        if not path.exists():
            return self._skip(f"Skipped: file not found {path}")

        if not _upload_required() and time.monotonic() < _CIRCUIT_OPEN_UNTIL:
            _log(f"Circuit open; local {file_type} used for {path.name}: {_CIRCUIT_REASON}")
            return None

        last_error = None
        retryable = True

        for attempt in range(1, self.retries + 1):
            try:
                with open(path, "rb") as file_obj:
                    response = self.session.post(
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

                if response.status_code in (400, 401, 403, 422):
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
                _log(f"Attempt {attempt}/{self.retries} failed for {path.name}: {exc}")
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
            _log(
                f"{_CONSECUTIVE_FAILURES} consecutive failures; "
                f"using local media for {self.circuit_open_seconds}s"
            )

        _log(f"Falling back to local file for {path.name}: {last_error}")
        return None


if __name__ == "__main__":
    # Self-test:  python media_uploader.py
    import tempfile

    tiny_jpg = bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909"
        "080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30"
        "313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000010501"
        "01010101010000000000000000000102030405060708090a0bffda0008010100003f00fbd3"
        "ffd9"
    )
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(tiny_jpg)

    url = MediaUploader().upload(tmp.name, "selftest", "screenshot", "selftest", "selftest")
    print("RESULT:", url if url else "FAILED (see [MEDIA] lines above)")