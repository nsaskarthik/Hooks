"""Structured, human-readable JSON logging.

Every log line follows the spec's shape:
    {timestamp, hook_name, category, status, duration_ms, ...}

Logs are written one pretty-printed JSON object per record to
``<log_dir>/<hook_name>.json`` is avoided in favour of an append-friendly
``.jsonl``-style file so concurrent hooks don't corrupt a shared array.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HookLogger:
    def __init__(self, log_dir: str | Path):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, hook_name: str, record: dict[str, Any]) -> None:
        """Append one structured record to ``<hook_name>.log.jsonl``."""
        entry = {"timestamp": _utc_now(), "hook_name": hook_name, **record}
        path = self.log_dir / f"{hook_name}.log.jsonl"
        try:
            with open(path, "a") as f:
                # Compact one-object-per-line keeps the file append-safe and still
                # greppable; use indent only when a human asks via `jq`.
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            # Logging must never break a hook.
            pass


def get_logger(log_dir: str | Path | None = None) -> HookLogger:
    if log_dir is None:
        from .config import get_config

        log_dir = get_config().log_dir
    return HookLogger(log_dir)
