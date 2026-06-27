#!/usr/bin/env python3
"""PreCompact hook - audit compaction, optionally back up the transcript.

Improves on v1: structured audit (trigger + whether custom instructions were
given), and an env-gated transcript backup (``BACKUP_TRANSCRIPT=true``). Fails open.
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.events import audit_event   # noqa: E402


def _backup(transcript_path: str, log_dir: Path, trigger: str) -> str | None:
    """Copy the transcript to a timestamped backup; return its path or None."""
    try:
        if not transcript_path or not Path(transcript_path).exists():
            return None
        backups = log_dir / "transcript_backups"
        backups.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # Clamp trigger to a safe filename fragment so it can't escape the dir.
        safe_trigger = re.sub(r"[^A-Za-z0-9_.-]+", "_", trigger).strip("._") or "unknown"
        dest = backups / f"{Path(transcript_path).stem}_{safe_trigger}_{stamp}.jsonl"
        shutil.copy2(transcript_path, dest)
        return str(dest)
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    """Read the PreCompact event, audit it, optionally back up the transcript."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        trigger = input_data.get("trigger", "unknown")
        extra = {"trigger": trigger,
                 "custom_instructions": bool(input_data.get("custom_instructions"))}
        if str(os.getenv("BACKUP_TRANSCRIPT", "")).strip().lower() in ("1", "true", "yes", "on"):
            path = _backup(input_data.get("transcript_path", ""), config.log_dir, trigger)
            if path:
                extra["backup"] = path
        audit_event("PreCompact", input_data, extra=extra, config=config)
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
