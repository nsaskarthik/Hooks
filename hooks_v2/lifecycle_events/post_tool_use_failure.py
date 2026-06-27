#!/usr/bin/env python3
"""PostToolUseFailure hook - audit the failure AND raise a notification.

A failing tool (including the Agent tool, i.e. a subagent that couldn't complete)
is audited with ``status=error`` and pushed through the scalable notifier so it can
reach a desktop alert today and mobile push later. Fails open.
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.events import audit_event   # noqa: E402
from hooks_v2.shared.notify import notify        # noqa: E402


def main() -> None:
    """Read the PostToolUseFailure event, audit it, and notify."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        tool_name = input_data.get("tool_name", "")
        error = input_data.get("error", "")
        tool_input = input_data.get("tool_input", {}) or {}
        audit_event(
            "PostToolUseFailure", input_data, status="error",
            extra={"tool_name": tool_name, "tool_use_id": input_data.get("tool_use_id", ""),
                   "error": error,
                   "input_keys": sorted(tool_input.keys()) if isinstance(tool_input, dict) else []},
            config=config,
        )
        notify(f"{tool_name or 'tool'} failed: {str(error)[:200]}",
               level="error", event="PostToolUseFailure",
               meta={"tool_name": tool_name, "session_id": input_data.get("session_id", "")},
               config=config)
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
