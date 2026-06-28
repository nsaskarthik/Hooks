"""Tests for the human-readable artifact writer (rewrites, TDD, test results)."""

from pathlib import Path

from hooks.shared import artifacts


def _wire(monkeypatch, tmp_path):
    """Point both the project root and HOME at temp dirs so writes are isolated."""
    proj = tmp_path / "proj"
    home = tmp_path / "home"
    proj.mkdir()
    home.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("HOOK_ARTIFACTS", raising=False)
    return proj, home


def test_dirs_are_project_local_and_global(monkeypatch, tmp_path):
    proj, home = _wire(monkeypatch, tmp_path)
    dirs = artifacts.artifact_dirs()
    assert proj / ".claude" / "hook_artifacts" in dirs
    assert home / ".claude" / "projects" / "proj" / "hook_artifacts" in dirs


def test_record_rewrite_appends_in_both_places(monkeypatch, tmp_path):
    proj, home = _wire(monkeypatch, tmp_path)
    artifacts.record_rewrite("teh bug", "the bug", ["teh -> the"], session_id="s1", event="UserPromptSubmit")
    artifacts.record_rewrite("anther", "another", ["anther -> another"], session_id="s1")
    for base in (proj / ".claude" / "hook_artifacts",
                 home / ".claude" / "projects" / "proj" / "hook_artifacts"):
        text = (base / "llm_rewrites.md").read_text()
        assert text.count("Rewritten:") == 2          # appended, not overwritten
        assert "the bug" in text and "another" in text


def test_write_tdd_increments_version(monkeypatch, tmp_path):
    proj, _ = _wire(monkeypatch, tmp_path)
    v1 = artifacts.write_tdd([{"name": "csv", "criterion": "output is CSV"}], "convert json", session_id="s1")
    v2 = artifacts.write_tdd([{"name": "hdr", "criterion": "has header"}], "convert json", session_id="s1")
    assert v1 == 1 and v2 == 2
    base = proj / ".claude" / "hook_artifacts"
    assert (base / "Tdd_V1.md").exists() and (base / "Tdd_V2.md").exists()
    assert "output is CSV" in (base / "Tdd_V1.md").read_text()


def test_write_test_results_renders_summary(monkeypatch, tmp_path):
    proj, _ = _wire(monkeypatch, tmp_path)
    v = artifacts.write_test_results({
        "passed_tests": 1, "total_tests": 2, "pass_rate": 0.5, "cycle": 1,
        "model_used": "claude-sonnet-4-6",
        "results": [{"name": "csv", "passed": True, "reason": "ok"},
                    {"name": "hdr", "passed": False, "reason": "missing"}],
    }, session_id="s1")
    assert v == 1
    text = (proj / ".claude" / "hook_artifacts" / "TestResults_V1.md").read_text()
    assert "1/2 (50%)" in text and "❌ fail" in text and "✅ pass" in text


def test_disabled_writes_nothing(monkeypatch, tmp_path):
    proj, _ = _wire(monkeypatch, tmp_path)
    monkeypatch.setenv("HOOK_ARTIFACTS", "false")
    assert artifacts.write_tdd([{"name": "x", "criterion": "y"}], "p") is None
    assert artifacts.record_rewrite("a", "b") == []
    assert not (proj / ".claude" / "hook_artifacts").exists()
