"""Human-readable artifacts for the prompt-rewrite + TDD flow.

Writes three kinds of files so a future UI (and you, today) can inspect what the
hooks did, in BOTH a project-local folder and a global per-project folder:

  <project>/.claude/hook_artifacts/
  ~/.claude/projects/<project-name>/hook_artifacts/

Files:
  - ``llm_rewrites.md``   one file, APPENDED on every applied prompt rewrite.
  - ``Tdd_V<n>.md``       one NEW versioned file per generated TDD criteria set.
  - ``TestResults_V<n>.md`` one NEW versioned file per validation summary.

Everything here is best-effort and NEVER raises: a hook must not break because an
artifact couldn't be written. Disable with ``HOOK_ARTIFACTS=false``.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARTIFACT_SUBDIR = "hook_artifacts"


def enabled() -> bool:
    """Artifacts are on by default; set HOOK_ARTIFACTS=false to turn them off."""
    return str(os.getenv("HOOK_ARTIFACTS", "true")).strip().lower() in ("1", "true", "yes", "on")


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root(cwd: str = "") -> Path:
    """Resolve the project root: CLAUDE_PROJECT_DIR > payload cwd > process cwd."""
    return Path(os.getenv("CLAUDE_PROJECT_DIR") or cwd or os.getcwd())


def _safe_name(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "_-.") else "_" for c in name) or "project"


def artifact_dirs(cwd: str = "") -> list[Path]:
    """Return the (existing) artifact dirs: project-local + global per-project."""
    root = _project_root(cwd)
    name = _safe_name(root.name)
    candidates = [
        root / ".claude" / ARTIFACT_SUBDIR,                              # project-local
        Path.home() / ".claude" / "projects" / name / ARTIFACT_SUBDIR,   # global per-project
    ]
    dirs: list[Path] = []
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            dirs.append(d)
        except OSError:
            pass
    return dirs


def _next_version(dirs: list[Path], prefix: str) -> int:
    """Next ``<prefix>V<n>.md`` version across all dirs (max existing + 1)."""
    highest = 0
    for d in dirs:
        try:
            for f in d.glob(f"{prefix}V*.md"):
                tail = f.stem[len(prefix) + 1:]  # chars after "<prefix>V"
                if tail.isdigit():
                    highest = max(highest, int(tail))
        except OSError:
            pass
    return highest + 1


def record_rewrite(original: str, refined: str, corrections: list | None = None,
                   *, cwd: str = "", session_id: str = "", event: str = "") -> list[Path]:
    """Append one applied prompt rewrite to ``llm_rewrites.md`` in each dir."""
    if not enabled():
        return []
    dirs = artifact_dirs(cwd)
    corr = ", ".join(str(c) for c in (corrections or [])) or "—"
    block = (
        f"## {_ts()}  ({event or 'rewrite'})\n\n"
        f"- **session:** `{session_id or '—'}`\n"
        f"- **corrections:** {corr}\n\n"
        f"**Original:**\n\n```\n{original}\n```\n\n"
        f"**Rewritten:**\n\n```\n{refined}\n```\n\n---\n\n"
    )
    for d in dirs:
        try:
            with open(d / "llm_rewrites.md", "a", encoding="utf-8") as f:
                f.write(block)
        except OSError:
            pass
    return dirs


def write_tdd(tests: list[dict], prompt: str,
              *, cwd: str = "", session_id: str = "") -> int | None:
    """Write generated TDD criteria to a new ``Tdd_V<n>.md``; return the version."""
    if not enabled():
        return None
    dirs = artifact_dirs(cwd)
    if not dirs:
        return None
    version = _next_version(dirs, "Tdd_")
    lines = [f"# TDD criteria V{version}", "", f"- **generated:** {_ts()}",
             f"- **session:** `{session_id or '—'}`", "",
             "## Prompt", "", "```", prompt, "```", "", "## Acceptance criteria", ""]
    for i, t in enumerate(tests or [], 1):
        name = t.get("name", f"criterion_{i}") if isinstance(t, dict) else f"criterion_{i}"
        crit = t.get("criterion", "") if isinstance(t, dict) else str(t)
        lines.append(f"{i}. **{name}** — {crit}")
    content = "\n".join(lines) + "\n"
    for d in dirs:
        try:
            (d / f"Tdd_V{version}.md").write_text(content, encoding="utf-8")
        except OSError:
            pass
    return version


def write_test_results(validation: dict[str, Any],
                       *, cwd: str = "", session_id: str = "") -> int | None:
    """Write a validation summary to a new ``TestResults_V<n>.md``; return version."""
    if not enabled():
        return None
    dirs = artifact_dirs(cwd)
    if not dirs:
        return None
    version = _next_version(dirs, "TestResults_")
    passed = validation.get("passed_tests", 0)
    total = validation.get("total_tests", 0)
    rate = validation.get("pass_rate", 0.0)
    cycle = validation.get("cycle", "—")
    lines = [f"# Test results V{version}", "", f"- **generated:** {_ts()}",
             f"- **session:** `{session_id or '—'}`",
             f"- **cycle:** {cycle}", f"- **model:** {validation.get('model_used', '—')}",
             f"- **pass rate:** {passed}/{total} ({rate:.0%})", "",
             "## Per-criterion", "", "| Criterion | Result | Reason |", "|---|---|---|"]
    for r in validation.get("results", []):
        status = "✅ pass" if r.get("passed") else "❌ fail"
        reason = str(r.get("reason", "")).replace("|", "\\|")
        lines.append(f"| {r.get('name', '—')} | {status} | {reason} |")
    content = "\n".join(lines) + "\n"
    for d in dirs:
        try:
            (d / f"TestResults_V{version}.md").write_text(content, encoding="utf-8")
        except OSError:
            pass
    return version
