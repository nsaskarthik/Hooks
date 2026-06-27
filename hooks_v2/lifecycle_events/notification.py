#!/usr/bin/env python3
"""Notification hook - audit notifications, optionally raise a desktop alert.

Improves on v1 by dropping the heavy TTS stack in favor of a structured audit
record plus an optional, env-gated desktop notification
(``NOTIFY_DESKTOP=true``; uses notify-send / osascript if present). Fails open.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.events import audit_event   # noqa: E402


def _desktop_notify(message: str) -> None:
    """Best-effort desktop notification via notify-send or osascript."""
    try:
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", "Claude Code", message],
                           capture_output=True, timeout=5)
        elif shutil.which("osascript"):
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "Claude Code"'],
                capture_output=True, timeout=5)
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    """Read the Notification event, audit it, optionally notify the desktop."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        message = input_data.get("message", "")
        audit_event("Notification", input_data, extra={"message": message}, config=get_config())
        if str(os.getenv("NOTIFY_DESKTOP", "")).strip().lower() in ("1", "true", "yes", "on"):
            _desktop_notify(message or "Claude Code needs your attention")
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
