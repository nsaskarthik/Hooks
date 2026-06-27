"""Cross-process state for the TDD handshake.

The prompt hooks (UserPromptSubmit / UserPromptExpansion) store generated
acceptance criteria under ``tdd_<session_id>``; the Stop hook loads them to score
the final response and tracks the retry-cycle count. State is a small JSON file
per key under ``<log_dir>/state/``.

``make_key`` remains available for tool-scoped keying (prefer ``tool_use_id``,
else a ``session_id`` + input hash composite) if a per-tool handshake is needed.
"""

import hashlib
import json
from pathlib import Path
from typing import Any


def make_key(session_id: str, tool_use_id: str | None, tool_input: dict | None) -> str:
    """Return a stable state key for a tool call."""
    if tool_use_id:
        return f"tuid_{tool_use_id}"
    blob = json.dumps(tool_input or {}, sort_keys=True, default=str)
    digest = hashlib.sha256(f"{session_id}:{blob}".encode()).hexdigest()[:16]
    return f"hash_{digest}"


class ContextStore:
    def __init__(self, state_dir: str | Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Keys are already filesystem-safe (prefixed hex / id).
        safe = "".join(c for c in key if c.isalnum() or c in "_-")
        return self.state_dir / f"{safe}.json"

    def save(self, key: str, data: dict[str, Any]) -> None:
        try:
            with open(self._path(key), "w") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError:
            pass

    def load(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def clear(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError:
            pass
