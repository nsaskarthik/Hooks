#!/usr/bin/env python3
"""SubagentStart hook - audit subagent spawns. Fails open."""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.events import audit_event   # noqa: E402


def main() -> None:
    """Read the SubagentStart event and audit it."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        audit_event("SubagentStart", input_data,
                    extra={"agent_id": input_data.get("agent_id", ""),
                           "agent_type": input_data.get("agent_type", "")},
                    config=get_config())
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
