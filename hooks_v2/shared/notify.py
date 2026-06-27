"""Scalable, multi-channel notification dispatch.

:func:`notify` fans one message out to every *enabled channel*. Channels are
selected by config (``notify.channels`` / ``NOTIFY_CHANNELS``) and each is
fail-safe — a broken channel never breaks the caller or the other channels.

Adding a new channel (e.g. a mobile push / SMS provider) is just: write a
``_ch_<name>(message, level, event, meta, config)`` function and register it in
``_CHANNELS``. Callers (the Notification hook, failure hooks, …) never change.

Built-in channels:
  - ``log``     : structured record in the unified audit log (always cheap).
  - ``desktop`` : notify-send / osascript pop-up.
  - ``webhook`` : HTTP POST JSON to ``NOTIFY_WEBHOOK_URL`` — the extensibility
                  point for mobile push (ntfy.sh / Pushover / Slack / your own
                  backend) without code changes.
  - ``sms``     : placeholder for a future SMS/push provider (e.g. Twilio). No-op
                  until wired; documented so the channel name is reserved.
"""

import json
import os
import shutil
import subprocess
from typing import Any

from .config import get_config
from .logger import get_logger


def notify(message: str, *, level: str = "info", event: str = "",
           meta: dict | None = None, config=None) -> dict[str, str]:
    """Dispatch ``message`` to all enabled channels. Returns per-channel status."""
    config = config or get_config()
    meta = meta or {}
    result: dict[str, str] = {}
    for name in _enabled_channels(config):
        fn = _CHANNELS.get(name)
        if fn is None:
            result[name] = "unknown-channel"
            continue
        try:
            fn(message, level, event, meta, config)
            result[name] = "ok"
        except Exception as e:  # noqa: BLE001 - a channel must never break others
            result[name] = f"error:{e}"
    return result


def _enabled_channels(config) -> list[str]:
    """Resolve the active channel list (env override > config > default ['log'])."""
    raw = os.getenv("NOTIFY_CHANNELS")
    if raw is not None:
        return [c.strip() for c in raw.split(",") if c.strip()]
    return list(getattr(config, "notify_channels", ["log"]) or ["log"])


# --- channels ---

def _ch_log(message: str, level: str, event: str, meta: dict, config) -> None:
    """Write a structured notification record to the unified audit log."""
    record: dict[str, Any] = {"category": "notification", "level": level,
                              "event": event, "message": message}
    if meta:
        record["meta"] = meta
    get_logger(config.log_dir).log("notify", record)


def _ch_desktop(message: str, level: str, event: str, meta: dict, config) -> None:
    """Best-effort desktop pop-up via notify-send or osascript."""
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "Claude Code", message], capture_output=True, timeout=5)
    elif shutil.which("osascript"):
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "Claude Code"'],
            capture_output=True, timeout=5)


def _ch_webhook(message: str, level: str, event: str, meta: dict, config) -> None:
    """POST the notification as JSON to NOTIFY_WEBHOOK_URL (mobile-push backends)."""
    url = os.getenv("NOTIFY_WEBHOOK_URL")
    if not url:
        return
    import urllib.request
    body = json.dumps({"text": message, "level": level, "event": event, "meta": meta}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5)  # noqa: S310 - operator-configured URL


def _ch_sms(message: str, level: str, event: str, meta: dict, config) -> None:
    """Placeholder for a future SMS / mobile-push provider (e.g. Twilio).

    Intentionally a no-op until credentials and a provider are wired in. Reserved
    so ``NOTIFY_CHANNELS=...,sms`` is valid ahead of that work.
    """
    return


_CHANNELS = {
    "log": _ch_log,
    "desktop": _ch_desktop,
    "webhook": _ch_webhook,
    "sms": _ch_sms,
}
