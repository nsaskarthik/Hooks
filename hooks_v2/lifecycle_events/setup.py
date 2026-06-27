#!/usr/bin/env python3
"""Setup hook - one-time CI/script preparation (``--init`` / ``--maintenance``).

Improves on v1: structured audit record, concise project detection emitted as
context, and persists PROJECT_ROOT via CLAUDE_ENV_FILE when available. Fails open.
"""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.events import audit_event   # noqa: E402

PROJECT_MARKERS = [
    ("package.json", "Node.js"),
    ("pyproject.toml", "Python (pyproject)"),
    ("requirements.txt", "Python (requirements)"),
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("Makefile", "Makefile"),
]


def _detect(cwd: str) -> list[str]:
    """Return labels for recognized project-marker files under cwd."""
    found = []
    base = Path(cwd or ".")
    for fname, label in PROJECT_MARKERS:
        if (base / fname).exists():
            found.append(label)
    return found


def _persist_env(name: str, value: str) -> None:
    """Append an `export NAME=value` line to CLAUDE_ENV_FILE if it is set."""
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        try:
            with open(env_file, "a") as f:
                # shlex.quote so a path with quotes/$()/backticks can't execute
                # when the env file is sourced.
                f.write(f"export {name}={shlex.quote(value)}\n")
        except OSError:
            pass


def main() -> None:
    """Read the Setup event, log it, and emit project-detection context."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        cwd = input_data.get("cwd", os.getcwd())
        trigger = input_data.get("trigger", "init")
        detected = _detect(cwd)

        if trigger == "init":
            _persist_env("PROJECT_ROOT", cwd)

        audit_event("Setup", input_data,
                    extra={"trigger": trigger, "detected": detected}, config=config)

        context = f"Setup ({trigger}). Detected: {', '.join(detected) or 'none'}."
        print(json.dumps({
            "hookSpecificOutput": {"hookEventName": "Setup", "additionalContext": context}
        }))
        sys.exit(0)
    except Exception:  # noqa: BLE001 - fail open
        sys.exit(0)


if __name__ == "__main__":
    main()
