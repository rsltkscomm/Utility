import os

from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv()
load_dotenv(os.path.join(os.getcwd(), "environment.env"))

DEFAULT_MODEL = "claude-3-sonnet-20240229"


def _get_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured. Add it to environment.env or your shell environment."
        )

    return Anthropic(api_key=api_key)


def ask_claude(prompt, max_tokens=2000):
    response = _get_client().messages.create(
        model=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
        max_tokens=max_tokens,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
