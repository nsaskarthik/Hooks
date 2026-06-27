#!/usr/bin/env python3
"""Notification hook - fan notifications out through the scalable notifier.

Delegates to ``shared.notify`` so the same dispatch (log + any enabled channel:
desktop, webhook, future mobile push/SMS) is reused everywhere. Fails open.
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT.parent))

from hooks.shared.config import get_config   # noqa: E402
from hooks.shared.events import audit_event   # noqa: E402
from hooks.shared.notify import notify        # noqa: E402


def main() -> None:
    """Read the Notification event, audit it, and dispatch via the notifier."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        message = input_data.get("message", "") or "Claude Code needs your attention"
        audit_event("Notification", input_data, extra={"message": message}, config=config)
        notify(message, level="info", event="Notification",
               meta={"session_id": input_data.get("session_id", "")}, config=config)
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
