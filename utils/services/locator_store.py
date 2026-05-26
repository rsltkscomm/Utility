import os
import time
from typing import Any, Dict, Optional

import requests

from utils.services.healing_config import healing_enabled


class LocatorStoreError(Exception):
    pass


class LocatorStore:
    """HTTP client for shared healed locators on the media server."""

    _cache: Dict[str, str] = {}
    _api_warning_shown = False

    def __init__(self):
        self.base_url = os.getenv("MEDIA_SERVER_URL", "").rstrip("/")
        self.token = os.getenv("MEDIA_SERVER_TOKEN", "")
        self.enabled = healing_enabled()
        self.retries = int(os.getenv("MEDIA_UPLOAD_RETRIES", "3"))
        self.timeout = int(os.getenv("MEDIA_UPLOAD_TIMEOUT", "60"))

    def _cache_key(
        self, project: str, environment: str, page_class: str, locator_name: str
    ) -> str:
        return f"{project}|{environment}|{page_class}|{locator_name}"

    def _warn_api_missing(self):
        if LocatorStore._api_warning_shown:
            return
        LocatorStore._api_warning_shown = True
        print(
            "[LocatorStore] /locators API not found on media server (404). "
            "Deploy media-server/app/main.py and run healed_locators.sql on the VM. "
            "Tier-2 shared healing is disabled until then."
        )

    def get_healed(
        self,
        project: str,
        environment: str,
        page_class: str,
        locator_name: str,
    ) -> Optional[str]:
        if not self.enabled or not self.base_url:
            return None

        key = self._cache_key(project, environment, page_class, locator_name)
        if key in self._cache:
            return self._cache[key]

        last_error = None
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.get(
                    f"{self.base_url}/locators",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params={
                        "project": project,
                        "environment": environment,
                        "page_class": page_class,
                        "locator_name": locator_name,
                    },
                    timeout=self.timeout,
                )
                if response.status_code == 404:
                    try:
                        detail = response.json().get("detail", "")
                    except Exception:
                        detail = response.text
                    if detail == "Locator not found":
                        return None
                    if detail == "Not Found":
                        self._warn_api_missing()
                    return None
                response.raise_for_status()
                healed = response.json().get("healed_locator")
                if healed:
                    self._cache[key] = healed
                return healed
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 10))

        print(f"[LocatorStore] GET failed for {key}: {last_error}")
        return None

    def save_healed(
        self,
        project: str,
        environment: str,
        page_class: str,
        locator_name: str,
        original_locator: str,
        healed_locator: str,
        source: str = "ai",
        healed_by: Optional[str] = None,
        app_url_pattern: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled or not self.base_url:
            return None

        payload = {
            "project": project,
            "environment": environment,
            "page_class": page_class,
            "locator_name": locator_name,
            "original_locator": original_locator,
            "healed_locator": healed_locator,
            "source": source,
            "healed_by": healed_by or os.getenv("PYTEST_XDIST_WORKER", "local"),
            "app_url_pattern": app_url_pattern,
        }

        last_error = None
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.put(
                    f"{self.base_url}/locators",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code == 404:
                    try:
                        detail = response.json().get("detail", "")
                    except Exception:
                        detail = response.text
                    if detail == "Not Found":
                        self._warn_api_missing()
                    return None
                response.raise_for_status()
                key = self._cache_key(project, environment, page_class, locator_name)
                self._cache[key] = healed_locator
                return response.json()
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 10))

        print(f"[LocatorStore] PUT failed for {page_class}.{locator_name}: {last_error}")
        return None

    @classmethod
    def clear_session_cache(cls):
        cls._cache.clear()
