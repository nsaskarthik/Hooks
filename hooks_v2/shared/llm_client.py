"""Thin, mockable wrapper around the Anthropic client.

Tier A / Tier B call :func:`complete`. Tests monkeypatch :func:`complete` so they
run without an API key or network. All failures raise :class:`LLMError`; callers
decide whether to fail open.
"""

import json
import re
from typing import Any

from .errors import LLMError


def complete(
    model: str,
    system: str,
    user: str,
    *,
    max_tokens: int = 1024,
    timeout: int = 30,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Send a single-turn message and return ``{text, input_tokens, output_tokens, model}``.

    Raises :class:`LLMError` on any failure (missing key, import error, API error).
    """
    if not api_key:
        raise LLMError("No ANTHROPIC_API_KEY available")
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - environment dependent
        raise LLMError(f"anthropic package not installed: {e}") from e

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        )
        return {
            "text": text,
            "input_tokens": getattr(message.usage, "input_tokens", 0),
            "output_tokens": getattr(message.usage, "output_tokens", 0),
            "model": model,
        }
    except LLMError:
        raise
    except Exception as e:  # noqa: BLE001 - any SDK/network error becomes LLMError
        raise LLMError(str(e)) from e


def parse_json_object(text: str) -> dict[str, Any]:
    """Best-effort extraction of a single JSON object from model output.

    Handles raw JSON, ```json fenced blocks, and leading/trailing prose.
    Raises :class:`LLMError` if no object can be parsed.
    """
    text = (text or "").strip()
    # Strip ``` fences if present.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # Fall back to the first balanced { ... } span.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except (json.JSONDecodeError, ValueError) as e:
            raise LLMError(f"Unparseable JSON from model: {e}") from e
    raise LLMError("No JSON object found in model output")
