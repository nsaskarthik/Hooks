"""Tests for the tiered memory store writer."""

import json

from hooks.shared import memory


def _wire(monkeypatch, tmp_path):
    """Enable memory, point MEMORY_DIR at a temp dir, and stub git lookups."""
    monkeypatch.delenv("HOOK_MEMORY", raising=False)        # re-enable (autouse disabled it)
    monkeypatch.delenv("MEMORY_AUTOCOMMIT", raising=False)
    d = tmp_path / "mem"
    monkeypatch.setenv("MEMORY_DIR", str(d))
    monkeypatch.setattr(memory, "_changed_files", lambda cwd: ["hooks/x.py"])
    monkeypatch.setattr(memory, "_git",
                        lambda cwd, *a: "branchX" if "--abbrev-ref" in a else "abc123")
    return d


def test_capture_writes_entry_and_hot(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    e = memory.capture_entry({"session_id": "s1", "cwd": str(tmp_path)}, prompt="fix the bug")
    assert e and e["files"] == ["hooks/x.py"]
    lines = (d / "log" / "entries.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["prompt"] == "fix the bug"
    hot = (d / "HOT.md").read_text()
    assert "fix the bug" in hot and "branchX" in hot


def test_change_gate_skips_duplicate(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    assert memory.capture_entry({"session_id": "s1"}, prompt="p")
    # Identical signature (same files, no validation) -> skipped, no duplicate.
    assert memory.capture_entry({"session_id": "s1"}, prompt="p") is None
    assert len((d / "log" / "entries.jsonl").read_text().splitlines()) == 1


def test_capture_redacts_secret(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    e = memory.capture_entry({"session_id": "s1"}, prompt="use token=abc123 now")
    assert "abc123" not in e["prompt"] and "***" in e["prompt"]


def test_validation_makes_notable_without_files(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    monkeypatch.setattr(memory, "_changed_files", lambda cwd: [])
    e = memory.capture_entry(
        {"session_id": "s1"},
        validation={"pass_rate": 0.5, "passed_tests": 1, "total_tests": 2}, prompt="x")
    assert e and e["tests"]["total"] == 2


def test_read_hot_returns_digest_and_user_memory(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    memory.capture_entry({"session_id": "s1"}, prompt="remember this")
    (d / "user_memory.md").write_text("# User\nlikes TDD")
    out = memory.read_hot()
    assert "remember this" in out and "likes TDD" in out


def test_disabled_writes_nothing(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    monkeypatch.setenv("HOOK_MEMORY", "false")
    assert memory.capture_entry({"session_id": "s1"}, prompt="p") is None
    assert not (d / "log" / "entries.jsonl").exists()


def test_compact_rolls_old_entries(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    memory._ensure(d)
    warm = d / "log" / "entries.jsonl"
    warm.write_text("\n".join(json.dumps({"ts": str(i)})
                              for i in range(memory._WARM_MAX + 5)) + "\n")
    assert memory.compact_if_needed() is True
    assert len(warm.read_text().splitlines()) == memory._WARM_KEEP
    assert (d / "archive" / "entries.jsonl").exists()


def test_changed_files_returns_clean_paths(monkeypatch, tmp_path):
    import subprocess
    monkeypatch.delenv("HOOK_MEMORY", raising=False)
    repo = tmp_path / "r"
    repo.mkdir()

    def g(*a):
        subprocess.run(["git", *a], cwd=repo, capture_output=True)

    g("init")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (repo / "alpha.py").write_text("x")
    g("add", "-A")
    g("commit", "-m", "init")
    (repo / "alpha.py").write_text("y")     # modified tracked
    (repo / "beta.py").write_text("z")      # untracked
    files = memory._changed_files(str(repo))
    # Full, unchopped paths (regression: leading char was being eaten).
    assert "alpha.py" in files and "beta.py" in files


def test_commit_memory_off_by_default(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    # MEMORY_AUTOCOMMIT unset -> no-op even though memory is enabled.
    assert memory.commit_memory({"session_id": "s1"}) is False
