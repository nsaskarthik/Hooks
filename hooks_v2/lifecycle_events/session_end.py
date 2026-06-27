#!/usr/bin/env python3
"""SessionEnd hook - audit the session end and clean up stale TDD state.

Improves on v1: structured audit record with the end reason, plus it sweeps
orphaned ``tdd_*`` state files left in the context store (e.g. if a Stop hook
never ran). Fails open.
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.events import audit_event   # noqa: E402
from hooks_v2.context_manager.context import session_key  # noqa: E402


def main() -> None:
    """Read the SessionEnd event, log it, and clear leftover TDD state."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        removed = 0
        session_id = input_data.get("session_id", "")
        # Only clear THIS session's TDD state, not other concurrent sessions'.
        if session_id and config.state_dir.exists():
            target = config.state_dir / f"{session_key(session_id)}.json"
            if target.is_file():
                try:
                    target.unlink()
                    removed = 1
                except OSError:
                    pass
        audit_event("SessionEnd", input_data,
                    extra={"reason": input_data.get("reason", ""),
                           "stale_state_cleared": removed},
                    config=config)
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
