#!/usr/bin/env python3
"""SubagentStop hook - audit subagent completion, optionally summarize.

Improves on v1: structured audit, and an optional one-line task summary produced
through the v2 ``llm_client`` (so it uses the configured backend / your
subscription) instead of a direct Anthropic call. Summary is env-gated
(``SUBAGENT_SUMMARY=true``) and off by default. Fails open.
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT.parent))

import os  # noqa: E402

from hooks.shared.config import get_config   # noqa: E402
from hooks.shared.events import audit_event   # noqa: E402
from hooks.shared.transcript import last_assistant_text  # noqa: E402

_SUMMARY_SYSTEM = (
    "Summarize what a subagent accomplished in one short, plain sentence for an "
    "audit log. No preamble, just the sentence."
)


def _summary(task_text: str, config) -> str | None:
    """Return a one-line LLM summary of the subagent task, or None on any issue."""
    if not task_text or not config.llm_available:
        return None
    try:
        from hooks.shared import llm_client
        result = llm_client.complete(
            config.tier_a_model, _SUMMARY_SYSTEM, task_text[:2000],
            max_tokens=120, timeout=config.timeout_seconds,
            api_key=config.anthropic_api_key, backend=config.llm_backend,
        )
        return (result.get("text") or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    """Read the SubagentStop event, audit it, optionally add an LLM summary."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        extra = {"agent_id": input_data.get("agent_id", ""),
                 "agent_type": input_data.get("agent_type", "")}
        if str(os.getenv("SUBAGENT_SUMMARY", "")).strip().lower() in ("1", "true", "yes", "on"):
            # Summarize the subagent's actual final message (its real work), not
            # the agent_type label. Falls back to the type only if no transcript.
            work = last_assistant_text(input_data.get("transcript_path", "")) \
                or input_data.get("agent_type", "")
            summary = _summary(work, config)
            if summary:
                extra["summary"] = summary
        audit_event("SubagentStop", input_data, extra=extra, config=config)
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
