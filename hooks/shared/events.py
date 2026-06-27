"""Shared structured audit logging for lifecycle hooks.

Every lifecycle hook funnels one record into a single unified audit log
(``<log_dir>/audit.log.jsonl``) via :func:`audit_event`, so the whole session is
greppable in one place (an improvement over v1's scattered per-event JSON files).
Records share a common shape and the call never raises.
"""

from typing import Any

from .config import get_config
from .logger import get_logger


def audit_event(
    event: str,
    input_data: dict,
    *,
    extra: dict[str, Any] | None = None,
    status: str = "ok",
    config=None,
    logger=None,
) -> dict[str, Any]:
    """Append one structured lifecycle record to the unified audit log.

    ``extra`` adds event-specific fields. Returns the record. Never raises.
    """
    try:
        config = config or get_config()
        logger = logger or get_logger(config.log_dir)
        record = {
            "category": "lifecycle",
            "event": event,
            "status": status,
            "session_id": input_data.get("session_id", ""),
            "cwd": input_data.get("cwd", ""),
            "permission_mode": input_data.get("permission_mode", ""),
        }
        if extra:
            record.update(extra)
        logger.log("audit", record)
        return record
    except Exception:  # noqa: BLE001 - logging must never break a hook
        return {}
