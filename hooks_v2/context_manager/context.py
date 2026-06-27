"""Cross-process state for the TDD handshake.

The prompt hooks (UserPromptSubmit / UserPromptExpansion) store generated
acceptance criteria under ``tdd_<session_id>``; the Stop hook loads them to score
the final response and tracks the retry-cycle count. State is a small JSON file
per key under ``<log_dir>/state/``.

Both sides build the key via :func:`session_key` so the prompt hook and the Stop
hook can never drift apart. ``make_key`` remains available for tool-scoped keying
(prefer ``tool_use_id``, else a ``session_id`` + input hash composite).
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def session_key(session_id: str) -> str:
    """Stable per-session key for the prompt->Stop TDD handshake.

    A blank/missing ``session_id`` normalises to a single deterministic key rather
    than producing inconsistent paths, and the value is hashed so it is always
    filesystem-safe.
    """
    sid = session_id or "default"
    digest = hashlib.sha256(sid.encode()).hexdigest()[:16]
    return f"tdd_{digest}"


def make_key(session_id: str, tool_use_id: str | None, tool_input: dict | None) -> str:
    """Return a stable state key for a tool call (tool-scoped keying)."""
    if tool_use_id:
        return f"tuid_{tool_use_id}"
    blob = json.dumps(tool_input or {}, sort_keys=True, default=str)
    digest = hashlib.sha256(f"{session_id}:{blob}".encode()).hexdigest()[:16]
    return f"hash_{digest}"


class ContextStore:
    """Filesystem-backed key/value store for small JSON state blobs."""

    def __init__(self, state_dir: str | Path):
        """Create the store, ensuring ``state_dir`` exists."""
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        """Return the on-disk path for ``key`` (sanitised to stay in state_dir)."""
        # Keys are already filesystem-safe (prefixed hex / id).
        safe = "".join(c for c in key if c.isalnum() or c in "_-")
        return self.state_dir / f"{safe}.json"

    def save(self, key: str, data: dict[str, Any]) -> None:
        """Atomically write ``data`` as JSON under ``key``."""
        # Write to a temp file and atomically replace, so a concurrent load()
        # never sees a half-written file (which would break the handshake).
        path = self._path(key)
        try:
            with tempfile.NamedTemporaryFile(
                "w", dir=path.parent, delete=False, encoding="utf-8"
            ) as f:
                json.dump(data, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
                tmp_path = Path(f.name)
            os.replace(tmp_path, path)
        except OSError:
            pass

    def load(self, key: str) -> dict[str, Any] | None:
        """Return the stored dict for ``key``, or ``None`` if absent/unreadable."""
        path = self._path(key)
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def clear(self, key: str) -> None:
        """Delete the state file for ``key`` if it exists."""
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError:
            pass
