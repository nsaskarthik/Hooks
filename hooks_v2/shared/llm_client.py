"""Mockable single-turn LLM wrapper with two backends.

Tier A / Tier B call :func:`complete`, which dispatches to:
  - ``agent_sdk`` (default): the Claude Agent SDK ``query()``, authenticated by a
    Claude subscription (CLAUDE_CODE_OAUTH_TOKEN or a logged-in ``claude`` CLI) —
    no per-token API key needed.
  - ``api``: the Anthropic API directly (needs an API key, billed at API rates).

Tests monkeypatch :func:`complete` so they run without auth or network. All
failures raise :class:`LLMError`; callers decide whether to fail open.
"""

import asyncio
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
    backend: str = "agent_sdk",
) -> dict[str, Any]:
    """Send a single-turn message and return ``{text, input_tokens, output_tokens, model}``.

    Raises :class:`LLMError` on any failure (missing auth, import error, API error).
    """
    if backend == "api":
        return _complete_api(model, system, user, max_tokens=max_tokens,
                             timeout=timeout, api_key=api_key)
    return _complete_agent_sdk(model, system, user, timeout=timeout)


def _complete_api(model, system, user, *, max_tokens, timeout, api_key):
    """Call the Anthropic Messages API (pay-as-you-go, needs an API key)."""
    if not api_key:
        raise LLMError("No ANTHROPIC_API_KEY available")
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - environment dependent
        raise LLMError(f"anthropic package not installed: {e}") from e
    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        message = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            b.text for b in message.content if getattr(b, "type", "") == "text"
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


def _complete_agent_sdk(model, system, user, *, timeout):
    """Call the Claude Agent SDK query() as a single-turn, tool-free completion.

    Uses subscription auth (no API key). Safe to run from a hook because hooks
    execute as standalone subprocesses, so there is no already-running event loop.
    """
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    except ImportError as e:  # pragma: no cover - environment dependent
        raise LLMError(f"claude-agent-sdk not installed: {e}") from e

    async def _run():
        """Run the single-turn query and return (text, usage)."""
        options = ClaudeAgentOptions(
            system_prompt=system,
            model=model,
            allowed_tools=[],        # pure completion, no tools
            max_turns=1,             # single turn
            permission_mode="dontAsk",
        )
        text, usage = "", {}
        async for message in query(prompt=user, options=options):
            if isinstance(message, ResultMessage):
                text = getattr(message, "result", "") or ""
                usage = getattr(message, "usage", {}) or {}
                break
        return text, usage

    try:
        text, usage = asyncio.run(asyncio.wait_for(_run(), timeout=timeout))
    except (asyncio.TimeoutError, TimeoutError) as e:
        raise LLMError(f"agent sdk timed out after {timeout}s") from e
    except LLMError:
        raise
    except Exception as e:  # noqa: BLE001 - any SDK error becomes LLMError
        raise LLMError(str(e)) from e

    usage = usage or {}
    return {
        "text": text,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "model": model,
    }


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
    # Fall back to the first fully balanced { ... } span (brace-depth scan that
    # ignores braces inside strings), so trailing prose can't break valid JSON.
    start = text.find("{")
    if start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i, ch in enumerate(text[start:], start=start):
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except (json.JSONDecodeError, ValueError) as e:
                        raise LLMError(f"Unparseable JSON from model: {e}") from e
    raise LLMError("No JSON object found in model output")
