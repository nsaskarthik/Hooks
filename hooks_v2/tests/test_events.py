"""End-to-end tests for the lifecycle hooks (subprocess, deterministic paths).

These hooks need no LLM, so they're driven via subprocess and asserted against the
unified audit log and their stdout decisions.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

LE = Path(__file__).resolve().parents[1] / "lifecycle_events"


def _run(script: str, payload: dict, tmp_path: Path, env_extra: dict | None = None):
    env = dict(os.environ)
    for key in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ENABLE_TDD",
                "AUTO_ALLOW_READONLY", "NOTIFY_DESKTOP", "SUBAGENT_SUMMARY", "BACKUP_TRANSCRIPT"):
        env.pop(key, None)
    env["LLM_BACKEND"] = "api"
    env["HOOKS_LOG_DIR"] = str(tmp_path / "logs")
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([sys.executable, str(LE / script)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=30)
    return proc


def _audit(tmp_path: Path) -> list[dict]:
    f = tmp_path / "logs" / "audit.log.jsonl"
    if not f.exists():
        return []
    return [json.loads(ln) for ln in f.read_text().splitlines() if ln.strip()]


# --- audit logging baseline ---

def test_session_start_emits_context_and_audits(tmp_path):
    proc = _run("session_start.py", {"session_id": "s1", "source": "startup", "cwd": str(tmp_path)}, tmp_path)
    assert proc.returncode == 0
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    assert "flags" in out["additionalContext"]
    assert any(r["event"] == "SessionStart" for r in _audit(tmp_path))


def test_session_end_clears_stale_tdd_state(tmp_path):
    state = tmp_path / "logs" / "state"
    state.mkdir(parents=True)
    (state / "tdd_abc.json").write_text("{}")
    proc = _run("session_end.py", {"session_id": "s1", "reason": "clear"}, tmp_path)
    assert proc.returncode == 0
    assert not (state / "tdd_abc.json").exists()
    rec = [r for r in _audit(tmp_path) if r["event"] == "SessionEnd"][0]
    assert rec["stale_state_cleared"] == 1


def test_setup_emits_context(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    proc = _run("setup.py", {"session_id": "s1", "trigger": "init", "cwd": str(tmp_path)}, tmp_path)
    assert proc.returncode == 0
    assert "Node.js" in json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]


# --- PreToolUse safety ---

def test_pre_tool_use_blocks_rm_rf(tmp_path):
    proc = _run("pre_tool_use.py", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/x"}}, tmp_path)
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert any(r.get("status") == "denied" for r in _audit(tmp_path))


def test_pre_tool_use_blocks_env_read(tmp_path):
    proc = _run("pre_tool_use.py", {"tool_name": "Read", "tool_input": {"file_path": "/app/.env"}}, tmp_path)
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"


def test_pre_tool_use_allows_and_audits_safe_bash(tmp_path):
    proc = _run("pre_tool_use.py", {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, tmp_path)
    assert proc.returncode == 0 and proc.stdout.strip() == ""
    rec = [r for r in _audit(tmp_path) if r["event"] == "PreToolUse"][0]
    assert rec["command"] == "ls -la" and rec["status"] == "ok"


def test_pre_tool_use_allows_env_sample(tmp_path):
    proc = _run("pre_tool_use.py", {"tool_name": "Read", "tool_input": {"file_path": "/app/.env.sample"}}, tmp_path)
    assert proc.stdout.strip() == ""   # not blocked


# --- failures, permissions, notifications, subagents, compaction ---

def test_post_tool_use_failure_audits_error(tmp_path):
    proc = _run("post_tool_use_failure.py",
                {"session_id": "s1", "tool_name": "Bash", "error": "boom",
                 "tool_input": {"command": "x"}}, tmp_path)
    rec = [r for r in _audit(tmp_path) if r["event"] == "PostToolUseFailure"][0]
    assert rec["status"] == "error" and rec["error"] == "boom"


def test_permission_request_logs_only_by_default(tmp_path):
    proc = _run("permission_request.py", {"tool_name": "Read", "tool_input": {"file_path": "x"}}, tmp_path)
    assert proc.stdout.strip() == ""   # no auto-allow unless enabled
    assert any(r["event"] == "PermissionRequest" for r in _audit(tmp_path))


def test_permission_request_auto_allows_readonly_when_enabled(tmp_path):
    proc = _run("permission_request.py", {"tool_name": "Read", "tool_input": {"file_path": "x"}},
                tmp_path, env_extra={"AUTO_ALLOW_READONLY": "true"})
    assert json.loads(proc.stdout)["hookSpecificOutput"]["decision"]["behavior"] == "allow"


def test_notification_audits(tmp_path):
    _run("notification.py", {"session_id": "s1", "message": "need input"}, tmp_path)
    assert any(r["event"] == "Notification" for r in _audit(tmp_path))


def test_subagent_start_audits(tmp_path):
    _run("subagent_start.py", {"agent_id": "a1", "agent_type": "Explore"}, tmp_path)
    rec = [r for r in _audit(tmp_path) if r["event"] == "SubagentStart"][0]
    assert rec["agent_type"] == "Explore"


def test_subagent_stop_audits_without_summary(tmp_path):
    proc = _run("subagent_stop.py", {"agent_id": "a1", "agent_type": "Explore"}, tmp_path)
    rec = [r for r in _audit(tmp_path) if r["event"] == "SubagentStop"][0]
    assert "summary" not in rec   # off by default


def test_pre_and_post_compact_audit(tmp_path):
    _run("pre_compact.py", {"session_id": "s1", "trigger": "auto"}, tmp_path)
    _run("post_compact.py", {"session_id": "s1", "trigger": "auto"}, tmp_path)
    events = {r["event"] for r in _audit(tmp_path)}
    assert {"PreCompact", "PostCompact"} <= events


def test_stop_audits_even_when_tdd_disabled(tmp_path):
    proc = _run("stop.py", {"session_id": "s1", "transcript_path": "", "stop_hook_active": False}, tmp_path)
    assert proc.returncode == 0
    assert any(r["event"] == "Stop" for r in _audit(tmp_path))


def test_lifecycle_hooks_fail_open_on_bad_json(tmp_path):
    for script in ("session_start.py", "pre_tool_use.py", "notification.py", "stop.py"):
        env = dict(os.environ)
        env["HOOKS_LOG_DIR"] = str(tmp_path / "logs")
        proc = subprocess.run([sys.executable, str(LE / script)], input="not json",
                              capture_output=True, text=True, env=env, timeout=30)
        assert proc.returncode == 0
