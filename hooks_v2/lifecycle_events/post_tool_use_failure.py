#!/usr/bin/env python3
"""PostToolUseFailure hook - audit tool failures.

Improves on v1: one structured ``status=error`` record in the unified audit log
with the tool, the error, and the input keys (not the full payload). Fails open.
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.events import audit_event   # noqa: E402


def main() -> None:
    """Read the PostToolUseFailure event and audit it."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        tool_input = input_data.get("tool_input", {}) or {}
        audit_event(
            "PostToolUseFailure", input_data, status="error",
            extra={
                "tool_name": input_data.get("tool_name", ""),
                "tool_use_id": input_data.get("tool_use_id", ""),
                "error": input_data.get("error", ""),
                "input_keys": sorted(tool_input.keys()) if isinstance(tool_input, dict) else [],
            },
            config=get_config(),
        )
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
