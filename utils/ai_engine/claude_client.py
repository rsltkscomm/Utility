import os

from anthropic import Anthropic
from utils.ini_file_reader.config_reader import ConfigReader

DEFAULT_MODEL = "claude-3-sonnet-20240229"


def _get_client():
    api_key = ConfigReader.get_property("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured. Add it to newenv.ini or your shell environment."
        )

    return Anthropic(api_key=api_key)


def ask_claude(prompt, max_tokens=2000):
    model = ConfigReader.get_property("ANTHROPIC_MODEL", DEFAULT_MODEL) or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
    response = _get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
