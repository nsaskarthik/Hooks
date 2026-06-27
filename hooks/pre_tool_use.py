#!/usr/bin/env python3
"""PreToolUse hook - block dangerous actions and audit Bash commands.

Ports v1's destructive-command and .env guards, improved:
  - decisions use JSON ``permissionDecision: deny`` (enforced even in bypass mode),
    not exit-2;
  - a wider dangerous-pattern set (rm -rf, dd, mkfs, fork bomb, chmod -R 777 /,
    overwrite of block devices);
  - every Bash command and every deny is written to the unified audit log.
Fails open: anything unexpected -> exit 0, tool proceeds.
"""

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT.parent))

from hooks.shared.config import get_config   # noqa: E402
from hooks.shared.events import audit_event   # noqa: E402

_RM_PATTERNS = [
    r"\brm\s+.*-[a-z]*r[a-z]*f",      # rm -rf / -fr / -Rf ...
    r"\brm\s+.*-[a-z]*f[a-z]*r",
    r"\brm\s+--recursive\s+--force",
    r"\brm\s+--force\s+--recursive",
]
_DANGEROUS = [
    r"\bdd\s+if=.*of=/dev/",          # overwrite a block device
    r"\bmkfs(\.\w+)?\s+/dev/",        # format a device
    r":\(\)\s*\{\s*:\|:&\s*\}\s*;:",  # fork bomb
    r"\bchmod\s+-[a-z]*R[a-z]*\s+777\s+/",  # chmod -R 777 /
    r">\s*/dev/sd[a-z]",             # write to a raw disk
]
_RM_DANGER_TARGETS = [r"\s/(\s|$|\*)", r"\s~(/|\s|$)", r"\$HOME", r"\s\.\.(/|\s|$)"]


def _danger(command: str) -> str | None:
    """Return a reason string if the command is destructive, else None."""
    norm = " ".join(command.lower().split())
    for pat in _RM_PATTERNS:
        if re.search(pat, norm):
            return "recursive force-remove (rm -rf) blocked"
    if re.search(r"\brm\s+.*-[a-z]*r", norm):
        for tgt in _RM_DANGER_TARGETS:
            if re.search(tgt, norm):
                return "recursive rm targeting a sensitive path blocked"
    for pat in _DANGEROUS:
        if re.search(pat, norm):
            return "destructive system command blocked"
    return None


def _env_access(tool_name: str, tool_input: dict) -> bool:
    """True if the call touches a real .env file (allows .sample/.example)."""
    if tool_name in ("Read", "Edit", "MultiEdit", "Write"):
        fp = tool_input.get("file_path", "")
        return ".env" in fp and not fp.endswith((".env.sample", ".env.example"))
    if tool_name == "Bash":
        return bool(re.search(r"\b\.env\b(?!\.(sample|example))", tool_input.get("command", "")))
    return False


_SECRET_RE = re.compile(
    r"(?i)(authorization:\s*bearer\s+|bearer\s+|--password[=\s]+|--token[=\s]+|"
    r"password[=\s]+|token[=\s]+|secret[=\s]+|api[_-]?key[=\s]+)(\S+)"
)
_AWS_RE = re.compile(r"AKIA[0-9A-Z]{16}")


def _redact(command: str) -> str:
    """Mask common inline secrets so the audit log never becomes a secret sink."""
    out = _SECRET_RE.sub(lambda m: m.group(1) + "***", command or "")
    return _AWS_RE.sub("AKIA" + "*" * 16, out)


def _deny(reason: str) -> None:
    """Emit a PreToolUse deny decision with the given reason."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main() -> None:
    """Read the PreToolUse event, deny dangerous calls, audit Bash."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        tool_name = input_data.get("tool_name", "")
        tool_input = dict(input_data.get("tool_input", {}) or {})

        if _env_access(tool_name, tool_input):
            reason = "Access to .env files with secrets is blocked (use .env.sample)."
            audit_event("PreToolUse", input_data, status="denied",
                        extra={"tool_name": tool_name, "reason": reason}, config=config)
            _deny(reason)
            sys.exit(0)

        if tool_name == "Bash":
            command = tool_input.get("command", "")
            reason = _danger(command)
            if reason:
                audit_event("PreToolUse", input_data, status="denied",
                            extra={"tool_name": "Bash", "command": _redact(command), "reason": reason},
                            config=config)
                _deny(reason)
                sys.exit(0)
            # Audit (allow) every Bash command for the run log, secrets redacted.
            audit_event("PreToolUse", input_data,
                        extra={"tool_name": "Bash", "command": _redact(command)}, config=config)

        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
