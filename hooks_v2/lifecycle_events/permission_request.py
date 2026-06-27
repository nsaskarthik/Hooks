#!/usr/bin/env python3
"""PermissionRequest hook - audit permission prompts, optionally auto-allow reads.

Always audits the request. When ``AUTO_ALLOW_READONLY=true`` (off by default), it
auto-allows clearly read-only tools (Read/Glob/Grep and a safe Bash allowlist) so
you aren't prompted for them. Improves on v1 with structured audit + opt-in gating.

Note: PermissionRequest does not fire in non-interactive (-p) mode.
"""

import json
import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.events import audit_event   # noqa: E402

_SAFE_BASH = [
    r"^ls\b", r"^pwd\b", r"^echo\b", r"^cat\b(?!.*>)", r"^head\b", r"^tail\b",
    r"^wc\b", r"^which\b", r"^file\b", r"^stat\b",
    r"^git\s+(status|log|diff|show|branch|remote)\b",
]


def _is_readonly(tool_name: str, tool_input: dict) -> bool:
    """True if the tool call is clearly read-only (safe to auto-allow)."""
    if tool_name in ("Read", "Glob", "Grep"):
        return True
    if tool_name == "Bash":
        cmd = (tool_input.get("command") or "").strip()
        return any(re.search(p, cmd) for p in _SAFE_BASH)
    return False


def main() -> None:
    """Read the PermissionRequest event, audit it, optionally auto-allow reads."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        tool_name = input_data.get("tool_name", "")
        tool_input = dict(input_data.get("tool_input", {}) or {})
        auto = str(os.getenv("AUTO_ALLOW_READONLY", "")).strip().lower() in ("1", "true", "yes", "on")
        allow = auto and _is_readonly(tool_name, tool_input)

        audit_event("PermissionRequest", input_data,
                    extra={"tool_name": tool_name, "auto_allowed": allow}, config=get_config())

        if allow:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {"behavior": "allow"},
                }
            }))
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
