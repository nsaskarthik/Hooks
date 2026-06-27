#!/usr/bin/env python3
"""SessionStart hook - audit the session and inject project/flags context.

Improves on v1: context loading is on by default (no flag needed), reports the
active v2 feature flags and LLM backend so Claude knows what's enabled, and writes
a structured record to the unified audit log. Fails open.
"""

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.events import audit_event   # noqa: E402


def _git_summary(cwd: str) -> list[str]:
    """Return short git branch / uncommitted-count / recent-commit lines for cwd."""
    out = []
    try:
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=5, cwd=cwd or None)
        if branch.returncode == 0:
            out.append(f"Git branch: {branch.stdout.strip()}")
        status = subprocess.run(["git", "status", "--porcelain"],
                                capture_output=True, text=True, timeout=5, cwd=cwd or None)
        if status.returncode == 0:
            n = len([ln for ln in status.stdout.splitlines() if ln.strip()])
            if n:
                out.append(f"Uncommitted changes: {n} file(s)")
        log = subprocess.run(["git", "log", "--oneline", "-5"],
                             capture_output=True, text=True, timeout=5, cwd=cwd or None)
        if log.returncode == 0 and log.stdout.strip():
            out.append("Recent commits:\n" + log.stdout.strip())
    except Exception:  # noqa: BLE001
        pass
    return out


def main() -> None:
    """Read the SessionStart event, log it, and emit project + flags context."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        source = input_data.get("source", "unknown")
        audit_event("SessionStart", input_data,
                    extra={"source": source, "model": input_data.get("model", "")},
                    config=config)

        parts = [f"Session source: {source}"]
        parts += _git_summary(input_data.get("cwd", ""))
        parts.append(
            "Active hooks_v2 flags: "
            f"prompt_rewrite={'on' if config.always_rewrite else 'off'}, "
            f"tdd_validation={'on' if config.enable_tdd else 'off'}; "
            f"llm_backend={config.llm_backend}."
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(parts),
            }
        }))
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
