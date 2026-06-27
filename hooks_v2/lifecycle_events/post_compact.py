#!/usr/bin/env python3
"""PostCompact hook - audit completion of context compaction.

Not present in v1; added for full coverage. Records the compaction trigger so the
audit log captures the before/after pair (PreCompact + PostCompact). Fails open.
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.events import audit_event   # noqa: E402


def main() -> None:
    """Read the PostCompact event and audit it."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        audit_event("PostCompact", input_data,
                    extra={"trigger": input_data.get("trigger", "")}, config=get_config())
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
