"""Tiered memory store writer (durable knowledge for Claude Code).

Writes a small, durable memory under ``MEMORY_DIR`` (default: the in-repo
``claude-memory/`` folder). Tiers:
  - ``log/entries.jsonl``  WARM: append-only machine-readable history (searchable).
  - ``HOT.md``             bounded human digest injected at SessionStart.
  - ``archive/entries.jsonl`` COLD: rolled-up old entries.
  - ``user_memory.md``     GLOBAL: cross-project preferences / lessons (hand/LLM curated).

Everything here is **deterministic, fail-open, and never raises**. Gated by
``HOOK_MEMORY`` (default on). Capture is **change-gated**: an entry is written only
when a turn changed files (or carried a validation result), and never twice for the
same signature.

Auto-commit (``MEMORY_AUTOCOMMIT``, default OFF) commits ONLY the memory dir — intended
for when the store is its *own* git repo, so it does not pollute the code repo's history
while it lives inside ``Hooks``.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .redact import redact

_HOT_MAX = 8       # entries kept in the injected HOT digest
_WARM_MAX = 200    # entries.jsonl size that triggers compaction
_WARM_KEEP = 100   # entries kept in WARM after a compaction


def enabled() -> bool:
    """Memory is on by default; set HOOK_MEMORY=false to disable."""
    return str(os.getenv("HOOK_MEMORY", "true")).strip().lower() in ("1", "true", "yes", "on")


def _autocommit() -> bool:
    """Auto-commit is OFF by default (avoid polluting the code repo's history)."""
    return str(os.getenv("MEMORY_AUTOCOMMIT", "")).strip().lower() in ("1", "true", "yes", "on")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]   # hooks/shared/memory.py -> repo root


def memory_dir() -> Path:
    """Resolve the memory store dir: MEMORY_DIR env, else the in-repo claude-memory/."""
    raw = os.getenv("MEMORY_DIR")
    return Path(raw).expanduser() if raw else _repo_root() / "claude-memory"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(cwd: str, *args: str) -> str:
    """Run a read-only git command in ``cwd``; return stripped stdout or ""."""
    try:
        r = subprocess.run(["git", *args], cwd=cwd or None, capture_output=True,
                           text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _changed_files(cwd: str) -> list[str]:
    """Files changed vs HEAD plus untracked (excluding ignored). Clean paths, deduped.

    Uses ``diff --name-only`` + ``ls-files --others`` (which emit bare filenames) rather
    than ``status --porcelain`` whose 2-char status prefix is fragile once stripped.
    """
    tracked = _git(cwd, "diff", "--name-only", "HEAD")
    untracked = _git(cwd, "ls-files", "--others", "--exclude-standard")
    seen: set[str] = set()
    files: list[str] = []
    for out in (tracked, untracked):
        for ln in out.splitlines():
            name = ln.strip()
            if name and name not in seen:
                seen.add(name)
                files.append(name)
    return files


def _ensure(d: Path) -> None:
    """Create the tier dirs and a .gitignore for the local marker."""
    (d / "log").mkdir(parents=True, exist_ok=True)
    (d / "archive").mkdir(parents=True, exist_ok=True)
    gi = d / ".gitignore"
    if not gi.exists():
        gi.write_text(".meta.json\n")


def _signature(files: list[str], validation: dict | None) -> str:
    """A stable signature of this turn's notable state, for de-duping."""
    payload = {"files": sorted(files),
               "pass_rate": (validation or {}).get("pass_rate")}
    return json.dumps(payload, sort_keys=True)


def _marker(d: Path) -> Path:
    return d / ".meta.json"


def _read_marker(d: Path) -> str:
    try:
        return json.loads(_marker(d).read_text()).get("sig", "")
    except Exception:  # noqa: BLE001
        return ""


def _write_marker(d: Path, sig: str) -> None:
    try:
        _marker(d).write_text(json.dumps({"sig": sig, "ts": _ts()}))
    except OSError:
        pass


def _append_warm(d: Path, entry: dict) -> None:
    try:
        with open(d / "log" / "entries.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def _render_hot_line(e: dict) -> str:
    branch = e.get("branch", "?")
    head = e.get("head", "")
    loc = f"{branch}@{head}" if head else branch
    prompt = (e.get("prompt") or "").replace("\n", " ").strip()
    if len(prompt) > 120:
        prompt = prompt[:117] + "..."
    files = e.get("files") or []
    fpart = f" · {len(files)} file(s)" if files else ""
    tests = e.get("tests")
    tpart = f" · tests {tests.get('passed')}/{tests.get('total')}" if tests else ""
    return f"- `{e.get('ts','')}` [{loc}]{fpart}{tpart} — {prompt or '(no prompt)'}"


def _update_hot(d: Path) -> None:
    """Rebuild HOT.md from the last _HOT_MAX WARM entries (bounded, constant size)."""
    try:
        path = d / "log" / "entries.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        recent = []
        for ln in lines[-_HOT_MAX:]:
            try:
                recent.append(json.loads(ln))
            except (json.JSONDecodeError, ValueError):
                continue
        body = "\n".join(_render_hot_line(e) for e in reversed(recent)) or "_(empty)_"
        (d / "HOT.md").write_text(
            "# HOT digest\n\n"
            "_Bounded, newest-first. Injected at SessionStart. Auto-written; do not edit._\n\n"
            + body + "\n", encoding="utf-8")
    except OSError:
        pass


def capture_entry(payload: dict, *, validation: dict | None = None,
                  prompt: str | None = None) -> dict | None:
    """Append a deterministic memory entry when a turn was notable. Returns the entry
    or None (skipped/disabled). Never raises."""
    if not enabled():
        return None
    try:
        cwd = payload.get("cwd") or os.getcwd()
        files = _changed_files(cwd)
        if not files and validation is None:
            return None  # nothing notable this turn
        sig = _signature(files, validation)
        d = memory_dir()
        _ensure(d)
        if sig == _read_marker(d):
            return None  # identical to the last entry -> no duplicate
        if prompt is None:
            from .transcript import last_user_text
            prompt = last_user_text(payload.get("transcript_path", ""))
        entry: dict[str, Any] = {
            "ts": _ts(),
            "session": payload.get("session_id", ""),
            "branch": _git(cwd, "rev-parse", "--abbrev-ref", "HEAD"),
            "head": _git(cwd, "rev-parse", "--short", "HEAD"),
            "prompt": redact((prompt or "")[:500]),
            "files": files[:50],
        }
        if validation:
            entry["tests"] = {"pass_rate": validation.get("pass_rate"),
                              "passed": validation.get("passed_tests"),
                              "total": validation.get("total_tests")}
        _append_warm(d, entry)
        _update_hot(d)
        _write_marker(d, sig)
        return entry
    except Exception:  # noqa: BLE001 - memory must never break a hook
        return None


def compact_if_needed() -> bool:
    """Deterministically roll old WARM entries into archive/ when WARM grows too large.

    Returns True if a compaction happened. (LLM summarization is a later enhancement;
    this keeps WARM bounded with zero auth/cost.) Never raises.
    """
    if not enabled():
        return False
    try:
        d = memory_dir()
        warm = d / "log" / "entries.jsonl"
        if not warm.exists():
            return False
        lines = warm.read_text(encoding="utf-8").splitlines()
        if len(lines) <= _WARM_MAX:
            return False
        old, keep = lines[:-_WARM_KEEP], lines[-_WARM_KEEP:]
        with open(d / "archive" / "entries.jsonl", "a", encoding="utf-8") as f:
            f.write("\n".join(old) + "\n")
        warm.write_text("\n".join(keep) + "\n", encoding="utf-8")
        return True
    except Exception:  # noqa: BLE001
        return False


def read_hot() -> str:
    """Return the HOT digest + user memory for SessionStart injection ("" if none)."""
    if not enabled():
        return ""
    try:
        d = memory_dir()
        parts = []
        for name in ("HOT.md", "user_memory.md"):
            p = d / name
            if p.exists():
                txt = p.read_text(encoding="utf-8").strip()
                if txt:
                    parts.append(txt)
        return "\n\n".join(parts)
    except OSError:
        return ""


def commit_memory(payload: dict, message: str | None = None) -> bool:
    """Commit ONLY the memory dir, if MEMORY_AUTOCOMMIT is enabled. Never raises.

    Scoped to the memory dir via pathspec so it never sweeps up unrelated working
    changes. Default OFF so it doesn't pollute the code repo while memory lives inside it.
    """
    if not enabled() or not _autocommit():
        return False
    try:
        d = memory_dir()
        # Commit within whatever git repo owns the memory dir (its own repo, ideally).
        repo = str(d)
        subprocess.run(["git", "add", "--", "."], cwd=repo, capture_output=True, timeout=10)
        msg = message or f"memory: update {_ts()}"
        r = subprocess.run(["git", "commit", "-m", msg], cwd=repo,
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False
