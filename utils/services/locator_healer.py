import json
import re
from typing import Optional

import requests
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.services.healing_config import (
    ai_healing_enabled,
    ai_provider,
    anthropic_api_key,
    anthropic_model,
    max_dom_chars,
    openrouter_api_key,
    openrouter_base_url,
    openrouter_model,
)


class LocatorHealerError(Exception):
    pass


class LocatorHealer:
    """Generate a Playwright locator using Anthropic or OpenRouter."""

    def __init__(self):
        self.enabled = ai_healing_enabled()
        self.provider = ai_provider()
        self.max_dom_chars = max_dom_chars()
        self.anthropic_key = anthropic_api_key()
        self.anthropic_model = anthropic_model()
        self.openrouter_key = openrouter_api_key()
        self.openrouter_model = openrouter_model()
        self.openrouter_base_url = openrouter_base_url()

    def _truncate_snapshot(self, snapshot) -> str:
        try:
            text = json.dumps(snapshot, ensure_ascii=False)
        except TypeError:
            text = str(snapshot)
        if len(text) > self.max_dom_chars:
            return text[: self.max_dom_chars] + "\n... [truncated]"
        return text

    def _build_prompt(
        self,
        page: Page,
        original_locator: str,
        page_class: str,
        locator_name: str,
        last_error: str,
    ) -> str:
        try:
            if hasattr(page, "accessibility") and page.accessibility is not None:
                snapshot = self._truncate_snapshot(page.accessibility.snapshot())
            elif hasattr(page, "aria_snapshot"):
                snapshot = self._truncate_snapshot(page.aria_snapshot())
            else:
                snapshot = "No accessibility snapshot available."
        except Exception as e:
            snapshot = f"Error capturing snapshot: {e}"
        return (
            "You are a Playwright test automation expert. "
            "Return ONLY one valid Playwright selector string (css, xpath=, or text=). "
            "No markdown, no explanation, no quotes around the whole answer.\n\n"
            f"Page URL: {page.url}\n"
            f"Page class: {page_class}\n"
            f"Locator constant name: {locator_name}\n"
            f"Broken locator: {original_locator}\n"
            f"Playwright error: {last_error}\n\n"
            f"Accessibility tree (JSON):\n{snapshot}\n"
        )

    def _extract_selector(self, content: str) -> str:
        text = (content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        text = text.strip().strip('"').strip("'")
        first_line = text.splitlines()[0].strip() if text else ""
        return first_line or text

    def _call_anthropic(self, prompt: str) -> str:
        if not self.anthropic_key:
            raise LocatorHealerError("ANTHROPIC_API_KEY is not set")

        try:
            import anthropic
        except ImportError as exc:
            raise LocatorHealerError("anthropic package is not installed") from exc

        client = anthropic.Anthropic(api_key=self.anthropic_key)
        message = client.messages.create(
            model=self.anthropic_model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        parts = []
        for block in message.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return self._extract_selector("".join(parts))

    def _call_openrouter(self, prompt: str) -> str:
        if not self.openrouter_key:
            raise LocatorHealerError("OpenRouter API key is not set (OPENROUTER_API_KEY or autohealing.ini Apikey)")

        url = f"{self.openrouter_base_url}/chat/completions"
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.openrouter_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 256,
            },
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return self._extract_selector(content)

    def _call_llm(self, prompt: str) -> str:
        if self.provider == "openrouter":
            return self._call_openrouter(prompt)
        return self._call_anthropic(prompt)

    def validate_locator(self, page: Page, locator: str, timeout_ms: int = 5000) -> bool:
        if not locator:
            return False
        try:
            element = page.locator(locator).first
            if element.count() == 0:
                return False
            element.wait_for(state="visible", timeout=timeout_ms)
            return True
        except (PlaywrightTimeoutError, Exception):
            return False

    def generate_healed_locator(
        self,
        page: Page,
        original_locator: str,
        page_class: str,
        locator_name: str,
        last_error: str = "",
    ) -> Optional[str]:
        if not self.enabled:
            return None

        print(
            f"[LocatorHealer] Trying AI heal for {page_class}.{locator_name} "
            f"via {self.provider} ({self.openrouter_model if self.provider == 'openrouter' else self.anthropic_model})"
        )

        prompt = self._build_prompt(
            page, original_locator, page_class, locator_name, last_error
        )

        try:
            candidate = self._call_llm(prompt)
        except Exception as exc:
            print(f"[LocatorHealer] LLM call failed: {exc}")
            return None

        if self.validate_locator(page, candidate):
            return candidate

        print(
            f"[LocatorHealer] LLM candidate did not match visible element: {candidate}"
        )
        return None
