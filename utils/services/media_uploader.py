import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


class MediaUploadError(Exception):
    pass


class MediaUploader:
    def __init__(self):
        self.base_url = os.getenv("MEDIA_SERVER_URL", "").rstrip("/")
        self.token = os.getenv("MEDIA_SERVER_TOKEN", "")
        self.enabled = os.getenv("MEDIA_UPLOAD_ENABLED", "yes").lower() == "yes"
        self.retries = int(os.getenv("MEDIA_UPLOAD_RETRIES", "3"))
        self.timeout = int(os.getenv("MEDIA_UPLOAD_TIMEOUT", "60"))
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
        path = Path(file_path)
        if not self.enabled or not self.base_url or not path.exists():
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
                        timeout=self.timeout,
                    )

                response.raise_for_status()
                return self._public_url(response.json().get("file_url"))
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 10))

        raise MediaUploadError(f"Upload failed for {file_path}: {last_error}")
