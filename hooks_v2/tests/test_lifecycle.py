"""End-to-end tests for the entry-point hook scripts.

Subprocess tests cover deterministic no-LLM paths (MCP audit, fail-open).
In-process tests cover the LLM paths with a mocked client: prompt rewrite at
UserPromptSubmit (context injection) and UserPromptExpansion (true rewrite), and
the Stop-hook TDD validate/retry loop.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
POST = _ROOT / "lifecycle_events" / "post_tool_use.py"
SUBMIT = _ROOT / "lifecycle_events" / "user_prompt_submit.py"


# --- subprocess helpers ---

# Hook flags that must be cleared so inherited env can't change default behavior.
_HOOK_ENV = ("ANTHROPIC_API_KEY", "ENABLE_TDD", "ENABLE_PROMPT_REWRITE",
             "REFINE_CONFIDENCE_THRESHOLD")


def _run_script(script: Path, payload: dict, log_dir: Path, env_extra: dict | None = None):
    env = dict(os.environ)
    for key in _HOOK_ENV:
        env.pop(key, None)
    env["HOOKS_LOG_DIR"] = str(log_dir)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=30,
    )


def test_mcp_post_writes_audit_record(tmp_path):
    payload = {
        "tool_name": "mcp__github__search_code",
        "tool_input": {"query": "needle"},
        "tool_output": {"results": []},
        "session_id": "s1", "duration_ms": 42, "model": "claude-opus-4-8",
    }
    proc = _run_script(POST, payload, tmp_path)
    assert proc.returncode == 0
    rec = json.loads((tmp_path / "mcp_audit.log.jsonl").read_text().strip().splitlines()[-1])
    for field in ("timestamp", "request", "model_name", "tool_called",
                  "response", "response_status", "execution_duration_ms"):
        assert field in rec
    assert rec["tool_called"] == "mcp__github__search_code"


def test_post_noop_for_non_mcp_tool(tmp_path):
    proc = _run_script(POST, {"tool_name": "Bash", "tool_input": {"command": "ls"}}, tmp_path)
    assert proc.returncode == 0 and proc.stdout.strip() == ""


def test_submit_skips_without_api_key(tmp_path):
    proc = _run_script(SUBMIT, {"text": "fix teh bug", "session_id": "s1"}, tmp_path)
    assert proc.returncode == 0 and proc.stdout.strip() == ""


def test_submit_invalid_json_fails_open(tmp_path):
    env = dict(os.environ)
    for key in _HOOK_ENV:
        env.pop(key, None)
    env["HOOKS_LOG_DIR"] = str(tmp_path)
    proc = subprocess.run([sys.executable, str(SUBMIT)], input="not json",
                          capture_output=True, text=True, env=env, timeout=30)
    assert proc.returncode == 0 and proc.stdout.strip() == ""


# --- in-process helpers ---

def _prime_config(monkeypatch, tmp_path, **env):
    # Clear any inherited hook flags, then apply only the explicit overrides.
    for key in _HOOK_ENV:
        if key not in env:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HOOKS_LOG_DIR", str(tmp_path / "logs"))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from hooks_v2.shared.config import get_config
    return get_config(reload=True)


def _run_main(main_fn, payload: dict, monkeypatch) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        with pytest.raises(SystemExit) as exc:
            main_fn()
    assert exc.value.code == 0
    return buf.getvalue()


def test_submit_injects_corrected_context(tmp_path, monkeypatch, mock_llm):
    _prime_config(monkeypatch, tmp_path)
    mock_llm({"refined_prompt": "Fix the authentication bug in the login flow",
              "confidence_score": 0.95, "corrections": ["athentication -> authentication"]})
    from hooks_v2.lifecycle_events import user_prompt_submit
    out = _run_main(user_prompt_submit.main,
                    {"text": "fix the athentication bug in the logn flow", "session_id": "s1"},
                    monkeypatch)
    payload = json.loads(out)["hookSpecificOutput"]
    assert payload["hookEventName"] == "UserPromptSubmit"
    assert "Fix the authentication bug in the login flow" in payload["additionalContext"]


def test_submit_skips_slash_command(tmp_path, monkeypatch, mock_llm):
    _prime_config(monkeypatch, tmp_path)
    mock_llm({"refined_prompt": "x", "confidence_score": 0.9})
    from hooks_v2.lifecycle_events import user_prompt_submit
    out = _run_main(user_prompt_submit.main, {"text": "/deploy staging", "session_id": "s1"}, monkeypatch)
    assert out.strip() == ""   # slash commands handled by expansion, not here


def test_expansion_truly_rewrites_prompt(tmp_path, monkeypatch, mock_llm):
    _prime_config(monkeypatch, tmp_path)
    mock_llm({"refined_prompt": "Write and run tests for the login module, covering edge cases",
              "confidence_score": 0.95, "corrections": ["tets -> tests"]})
    from hooks_v2.lifecycle_events import user_prompt_expansion
    out = _run_main(user_prompt_expansion.main,
                    {"command_name": "/test", "expanded_prompt": "write tets for login",
                     "args": [], "session_id": "s1"}, monkeypatch)
    payload = json.loads(out)
    # True rewrite uses the top-level expandedPrompt field.
    assert payload["expandedPrompt"] == "Write and run tests for the login module, covering edge cases"


def test_stop_tdd_block_then_pass(tmp_path, monkeypatch, mock_llm):
    cfg = _prime_config(monkeypatch, tmp_path, ENABLE_TDD="true", ENABLE_PROMPT_REWRITE="false")
    assert cfg.enable_tdd

    # Seed criteria via the submit hook (Tier B generate).
    mock_llm({"tests": [{"name": "csv", "criterion": "output is CSV"}]})
    from hooks_v2.lifecycle_events import user_prompt_submit, stop
    _run_main(user_prompt_submit.main, {"text": "convert json to csv", "session_id": "sX"}, monkeypatch)

    # Build a transcript with a final assistant message.
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "still JSON output"}]}}
    ) + "\n")
    stop_payload = {"session_id": "sX", "transcript_path": str(transcript), "stop_hook_active": False}

    # Cycle 1: fails -> block.
    mock_llm({"results": [{"name": "csv", "passed": False, "reason": "not CSV"}]})
    blocked = json.loads(_run_main(stop.main, stop_payload, monkeypatch))
    assert blocked["decision"] == "block" and "csv" in blocked["reason"]

    # Cycle 2: passes -> no block.
    mock_llm({"results": [{"name": "csv", "passed": True, "reason": "ok"}]})
    assert _run_main(stop.main, stop_payload, monkeypatch).strip() == ""


def test_stop_noop_when_tdd_disabled(tmp_path, monkeypatch):
    _prime_config(monkeypatch, tmp_path)  # enable_tdd false by default
    from hooks_v2.lifecycle_events import stop
    out = _run_main(stop.main, {"session_id": "s1", "transcript_path": "", "stop_hook_active": False},
                    monkeypatch)
    assert out.strip() == ""


def test_expansion_no_output_when_prompt_unchanged(tmp_path, monkeypatch, mock_llm):
    _prime_config(monkeypatch, tmp_path)
    mock_llm({"refined_prompt": "run the tests", "confidence_score": 0.99})
    from hooks_v2.lifecycle_events import user_prompt_expansion
    out = _run_main(user_prompt_expansion.main,
                    {"command_name": "/test", "expanded_prompt": "run the tests",
                     "args": [], "session_id": "s1"}, monkeypatch)
    assert out.strip() == ""   # nothing to rewrite -> no expandedPrompt emitted


def test_submit_no_output_below_confidence(tmp_path, monkeypatch, mock_llm):
    _prime_config(monkeypatch, tmp_path, REFINE_CONFIDENCE_THRESHOLD="0.8")
    mock_llm({"refined_prompt": "a very different prompt", "confidence_score": 0.4})
    from hooks_v2.lifecycle_events import user_prompt_submit
    out = _run_main(user_prompt_submit.main, {"text": "orig", "session_id": "s1"}, monkeypatch)
    assert out.strip() == ""   # low confidence -> don't inject


def test_stop_respects_stop_hook_active(tmp_path, monkeypatch, mock_llm):
    cfg = _prime_config(monkeypatch, tmp_path, ENABLE_TDD="true", ENABLE_PROMPT_REWRITE="false")
    assert cfg.enable_tdd
    # Seed criteria so the only reason for no-op is the stop_hook_active guard.
    mock_llm({"tests": [{"name": "t1", "criterion": "c"}]})
    from hooks_v2.lifecycle_events import user_prompt_submit, stop
    _run_main(user_prompt_submit.main, {"text": "do x", "session_id": "sA"}, monkeypatch)

    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}}) + "\n")
    out = _run_main(stop.main,
                    {"session_id": "sA", "transcript_path": str(transcript), "stop_hook_active": True},
                    monkeypatch)
    assert out.strip() == ""   # already continuing once -> must not block again
