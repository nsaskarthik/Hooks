"""Shared secret redaction.

Lifted out of ``pre_tool_use.py`` so the same masking protects anything we persist
(audit logs, memory entries, artifacts) — memory files must never become a secret
sink. Best-effort and never raises.
"""

import re

# Inline credentials: `Authorization: Bearer x`, `--password=x`, `token=x`, etc.
_SECRET_RE = re.compile(
    r"(?i)(authorization:\s*bearer\s+|bearer\s+|--password[=\s]+|--token[=\s]+|"
    r"password[=\s]+|token[=\s]+|secret[=\s]+|api[_-]?key[=\s]+)(\S+)"
)
# AWS access key ids.
_AWS_RE = re.compile(r"AKIA[0-9A-Z]{16}")


def redact(text: str) -> str:
    """Mask common inline secrets in ``text``. Returns "" for falsy input."""
    out = _SECRET_RE.sub(lambda m: m.group(1) + "***", text or "")
    return _AWS_RE.sub("AKIA" + "*" * 16, out)
