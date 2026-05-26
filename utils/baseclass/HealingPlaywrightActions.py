import inspect
import os
from typing import Any, Callable, Optional, Tuple

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.baseclass.PW_BaseClass import PlaywrightActions
from utils.constants.framework_constants import FrameworkConstants
from utils.ini_file_reader.config_reader import ConfigReader

from utils.services.healing_config import ai_healing_enabled

from utils.services.locator_store import LocatorStore


class HealingPlaywrightActions(PlaywrightActions):
    """Three-tier locator resolution: original -> shared store -> AI."""

    def __init__(self, page):
        super().__init__(page)
        self._store = LocatorStore()
        self._healer = LocatorHealer()
        self._healing_enabled = healing_enabled()
        self._on_heal_callbacks = []

    def register_heal_callback(self, callback: Callable[[str], None]):
        self._on_heal_callbacks.append(callback)

    def _notify_heal(self, message: str):
        print(message)
        for callback in self._on_heal_callbacks:
            try:
                callback(message)
            except Exception:
                pass

    def _project_name(self) -> str:
        return os.getenv("PROJECT_NAME") or FrameworkConstants.PROJECT_NAME or "Resul"

    def _environment_name(self) -> str:
        env = os.getenv("Environment", "").strip()
        if not env:
            try:
                env = ConfigReader.get_property("Environment", "default") or "default"
            except Exception:
                env = "default"
        return str(env).strip().lower()

    def _resolve_locator_identity(self, locator: str) -> Tuple[Optional[str], Optional[str]]:
        """Infer page_class and locator_name from the calling page object frame."""
        frame = inspect.currentframe()
        if frame is None:
            return None, None

        for _ in range(12):
            frame = frame.f_back
            if frame is None:
                break
            caller_self = frame.f_locals.get("self")
            if caller_self is None:
                continue
            page_class = caller_self.__class__.__name__
            if page_class in ("HealingPlaywrightActions", "PlaywrightActions"):
                continue
            if not page_class.endswith("Page"):
                continue

            for cls in caller_self.__class__.__mro__:
                if cls.__name__ in ("object", "PlaywrightActions", "HealingPlaywrightActions"):
                    continue
                for name, value in vars(cls).items():
                    if not name.isupper():
                        continue
                    if isinstance(value, str) and value == locator:
                        return cls.__name__, name
            return page_class, None

        return None, None

    def _try_locator(self, locator: str, action_fn: Callable[[str], Any]) -> Any:
        return action_fn(locator)

    def _execute_with_healing(
        self,
        locator: str,
        action_fn: Callable[[str], Any],
        *,
        allow_false: bool = False,
    ) -> Any:
        if not self._healing_enabled:
            return action_fn(locator)

        page_class, locator_name = self._resolve_locator_identity(locator)
        project = self._project_name()
        environment = self._environment_name()
        last_error = ""

        if not page_class or not locator_name:
            print(
                f"[HEAL] Could not resolve locator identity for: {locator[:80]}... "
                "Call from a *Page method using a class constant."
            )

        tiers = [("original", locator)]

        if page_class and locator_name:
            healed = self._store.get_healed(
                project, environment, page_class, locator_name
            )
            if healed and healed != locator:
                tiers.append(("store", healed))

        for source, candidate in tiers:
            try:
                result = self._try_locator(candidate, action_fn)
                if source != "original" and page_class and locator_name:
                    self._notify_heal(
                        f"[HEAL] {page_class}.{locator_name}: used {source} locator -> {candidate}"
                    )
                return result
            except (PlaywrightTimeoutError, Exception) as exc:
                last_error = str(exc)
                if source == "original":
                    continue
                if source == "store":
                    continue

        if (
            self._healing_enabled
            and page_class
            and locator_name
            and ai_healing_enabled()
        ):
            ai_locator = self._healer.generate_healed_locator(
                self.page,
                locator,
                page_class,
                locator_name,
                last_error,
            )
            if ai_locator:
                try:
                    result = self._try_locator(ai_locator, action_fn)
                    self._store.save_healed(
                        project=project,
                        environment=environment,
                        page_class=page_class,
                        locator_name=locator_name,
                        original_locator=locator,
                        healed_locator=ai_locator,
                        source="ai",
                    )
                    self._notify_heal(
                        f"[HEAL] {page_class}.{locator_name}: {locator} -> {ai_locator} (source: ai)"
                    )
                    return result
                except (PlaywrightTimeoutError, Exception) as exc:
                    last_error = str(exc)

        if allow_false:
            return False
        raise PlaywrightTimeoutError(
            f"Locator failed after healing tiers for {page_class}.{locator_name}: {last_error}"
        )

    def click_element(self, locator):
        return self._execute_with_healing(
            locator,
            lambda loc: super(HealingPlaywrightActions, self).click_element(loc),
        )

    def enter_value(self, locator, value):
        return self._execute_with_healing(
            locator,
            lambda loc: super(HealingPlaywrightActions, self).enter_value(loc, value),
        )

    def _require_visible(self, locator: str, timeout: int = 15000) -> bool:
        if not super().wait_for_element(locator, timeout):
            raise PlaywrightTimeoutError(f"Element not visible: {locator}")
        return True

    def _require_present(self, locator: str) -> bool:
        if not super().is_element_present(locator):
            raise PlaywrightTimeoutError(f"Element not present: {locator}")
        return True

    def _require_clear(self, locator: str) -> bool:
        if not super().clear_field(locator):
            raise PlaywrightTimeoutError(f"Could not clear field: {locator}")
        return True

    def _require_upload(self, locator: str, file_name: str) -> bool:
        if not super().upload_file(locator, file_name):
            raise PlaywrightTimeoutError(f"Could not upload to: {locator}")
        return True

    def wait_for_element(self, locator, timeout=15000):
        if not self._healing_enabled:
            return super().wait_for_element(locator, timeout)
        try:
            return self._execute_with_healing(
                locator,
                lambda loc: self._require_visible(loc, timeout),
            )
        except PlaywrightTimeoutError:
            return False

    def is_element_present(self, locator) -> bool:
        if not self._healing_enabled:
            return super().is_element_present(locator)
        try:
            self._execute_with_healing(
                locator,
                lambda loc: self._require_present(loc),
            )
            return True
        except PlaywrightTimeoutError:
            return False

    def get_value(self, locator):
        return self._execute_with_healing(
            locator,
            lambda loc: super(HealingPlaywrightActions, self).get_value(loc),
        )

    def clear_field(self, locator):
        if not self._healing_enabled:
            return super().clear_field(locator)
        try:
            return self._execute_with_healing(
                locator,
                lambda loc: self._require_clear(loc),
            )
        except PlaywrightTimeoutError:
            return False

    def upload_file(self, locator, file_name) -> bool:
        if not self._healing_enabled:
            return super().upload_file(locator, file_name)
        try:
            return self._execute_with_healing(
                locator,
                lambda loc: self._require_upload(loc, file_name),
            )
        except PlaywrightTimeoutError:
            return False

    def get_attribute(self, locator, attribute):
        return self._execute_with_healing(
            locator,
            lambda loc: super(HealingPlaywrightActions, self).get_attribute(
                loc, attribute
            ),
        )

    def is_visible(self, locator):
        if not self._healing_enabled:
            return super().is_visible(locator)
        try:
            return bool(
                self._execute_with_healing(
                    locator,
                    lambda loc: super(HealingPlaywrightActions, self).is_visible(loc),
                )
            )
        except PlaywrightTimeoutError:
            return False

    def get_text(self, locator):
        return self._execute_with_healing(
            locator,
            lambda loc: super(HealingPlaywrightActions, self).get_text(loc),
        )

    def js_click(self, locator):
        return self._execute_with_healing(
            locator,
            lambda loc: super(HealingPlaywrightActions, self).js_click(loc),
        )

    def is_enabled(self, locator):
        return self._execute_with_healing(
            locator,
            lambda loc: super(HealingPlaywrightActions, self).is_enabled(loc),
        )

    def select_list_elements(self, elements_path, input_text):
        return self._execute_with_healing(
            elements_path,
            lambda loc: super(HealingPlaywrightActions, self).select_list_elements(
                loc, input_text
            ),
            allow_false=True,
        )
