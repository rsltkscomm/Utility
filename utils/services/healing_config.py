import os

from utils.ini_file_reader.config_reader import ConfigReader


def _truthy(value, default="yes") -> bool:
    if value is None:
        return default.lower() in ("yes", "true", "1")
    return str(value).strip().lower() in ("yes", "true", "1")


def healing_enabled() -> bool:
    env = os.getenv("HEALING_ENABLED")
    if env is not None:
        return _truthy(env)
    try:
        return _truthy(ConfigReader.get_property("selfhealing", "yes"))
    except Exception:
        return True


def ai_healing_enabled() -> bool:
    env = os.getenv("HEALING_AI_ENABLED")
    if env is not None:
        return _truthy(env)
    try:
        return _truthy(ConfigReader.get_property("aihealing", "yes"))
    except Exception:
        return True


def ai_provider() -> str:
    env = os.getenv("HEALING_AI_PROVIDER", "").strip().lower()
    ini_key = openrouter_api_key()
    if ini_key and env in ("", "anthropic"):
        return "openrouter"
    if env:
        return env
    if ini_key:
        return "openrouter"
    return "anthropic"


def openrouter_api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    try:
        return (ConfigReader.get_property("Apikey", "") or "").strip()
    except Exception:
        return ""


def openrouter_base_url() -> str:
    env = os.getenv("OPENROUTER_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    try:
        return (ConfigReader.get_property("BaseURI", "https://openrouter.ai/api/v1") or "").rstrip("/")
    except Exception:
        return "https://openrouter.ai/api/v1"


def openrouter_model() -> str:
    env = os.getenv("OPENROUTER_MODEL", "").strip()
    if env:
        return env
    try:
        return ConfigReader.get_property("model", "anthropic/claude-sonnet-4") or "anthropic/claude-sonnet-4"
    except Exception:
        return "anthropic/claude-sonnet-4"


def anthropic_api_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "").strip()


def anthropic_model() -> str:
    return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def max_dom_chars() -> int:
    try:
        return int(os.getenv("HEALING_MAX_DOM_CHARS", "12000"))
    except ValueError:
        return 12000
