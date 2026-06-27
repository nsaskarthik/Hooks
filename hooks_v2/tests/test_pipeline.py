"""Tests for the shared Tier A/B prompt pipeline and audit edge cases."""

from hooks_v2.category1 import mcp_audit
from hooks_v2.category2 import pipeline
from hooks_v2.context_manager.context import ContextStore, session_key
from hooks_v2.shared.logger import HookLogger


def _logger(tmp_path):
    return HookLogger(tmp_path / "logs")


def test_pipeline_applies_refinement(config, tmp_path, mock_llm):
    mock_llm({"refined_prompt": "Corrected prompt", "confidence_score": 0.9,
              "corrections": ["teh -> the"]})
    out = pipeline.refine_and_prepare("teh prompt", "s1", config, _logger(tmp_path), "UserPromptSubmit")
    assert out["applied"] is True and out["refined"] == "Corrected prompt"


def test_pipeline_no_apply_when_rewrite_disabled(config, tmp_path, mock_llm):
    config.always_rewrite = False
    mock_llm({"refined_prompt": "x", "confidence_score": 1.0})
    out = pipeline.refine_and_prepare("anything", "s1", config, _logger(tmp_path), "UserPromptSubmit")
    assert out["applied"] is False and out["refined"] == "anything"


def test_pipeline_generates_tdd_when_enabled(config, tmp_path, monkeypatch, mock_llm):
    config.always_rewrite = False
    config.enable_tdd = True

    # Two-call script: refine (unused here) then test generation.
    def responder(model, system, user):
        if "test designer" in system.lower():
            return {"tests": [{"name": "t1", "criterion": "c"}]}
        return {"refined_prompt": user, "confidence_score": 0.0}

    mock_llm(responder)
    pipeline.refine_and_prepare("build a parser", "sess9", config, _logger(tmp_path), "UserPromptExpansion")
    state = ContextStore(config.state_dir).load(session_key("sess9"))
    assert state and state["tests"][0]["name"] == "t1" and state["cycle"] == 0


def test_pipeline_tdd_failure_is_swallowed(config, tmp_path, monkeypatch):
    config.always_rewrite = False
    config.enable_tdd = True
    from hooks_v2.shared import llm_client
    from hooks_v2.shared.errors import LLMError

    monkeypatch.setattr(llm_client, "complete", lambda *a, **k: (_ for _ in ()).throw(LLMError("x")))
    # Must not raise even though TDD generation fails.
    out = pipeline.refine_and_prepare("p", "s1", config, _logger(tmp_path), "UserPromptSubmit")
    assert out["applied"] is False


def test_mcp_audit_marks_error_status():
    rec = mcp_audit.build_audit_record({
        "tool_name": "mcp__db__query", "tool_input": {"sql": "x"},
        "tool_output": {"error": "boom"}, "duration_ms": 5,
    })
    assert rec["status"] == "error" and rec["response_status"] == "error"
