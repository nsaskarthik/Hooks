"""Tests for Tier A (prompt rewrite) and Tier B (TDD)."""

from hooks import tier_a_refine, tier_b_tdd


# --- Tier A ---

def test_refine_fixes_typos_and_applies(config, mock_llm):
    mock_llm({
        "refined_prompt": "Fix the authentication bug in the login endpoint",
        "confidence_score": 0.95,
        "corrections": ["athentication -> authentication", "logn -> login"],
        "ambiguities": [],
    })
    out = tier_a_refine.refine_prompt("fix the athentication bug in the logn endpoint", config)
    assert out["status"] == "success"
    assert out["refined_prompt"] == "Fix the authentication bug in the login endpoint"
    assert tier_a_refine.should_apply(out, config) is True


def test_refine_skips_without_api_key(config, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config.anthropic_api_key = None
    out = tier_a_refine.refine_prompt("do the thing", config)
    assert out["status"] == "skipped"
    assert out["refined_prompt"] == "do the thing"          # original preserved
    assert tier_a_refine.should_apply(out, config) is False


def test_refine_empty_prompt(config):
    out = tier_a_refine.refine_prompt("   ", config)
    assert out["status"] == "skipped"


def test_refine_fails_open_on_llm_error(config, monkeypatch):
    from hooks.shared import llm_client
    from hooks.shared.errors import LLMError

    def boom(*a, **k):
        raise LLMError("network down")

    monkeypatch.setattr(llm_client, "complete", boom)
    out = tier_a_refine.refine_prompt("anything", config)
    assert out["status"] == "error"
    assert out["refined_prompt"] == "anything"              # original preserved


def test_should_not_apply_when_unchanged(config, mock_llm):
    mock_llm({"refined_prompt": "same prompt", "confidence_score": 0.99})
    out = tier_a_refine.refine_prompt("same prompt", config)
    assert tier_a_refine.should_apply(out, config) is False


def test_should_not_apply_below_confidence(config, mock_llm):
    config.refine_confidence_threshold = 0.8
    mock_llm({"refined_prompt": "a different prompt", "confidence_score": 0.5})
    out = tier_a_refine.refine_prompt("orig prompt", config)
    assert tier_a_refine.should_apply(out, config) is False


# --- Tier B ---

def test_generate_tests(config, mock_llm):
    mock_llm({"tests": [{"name": "t1", "criterion": "returns CSV"}]})
    out = tier_b_tdd.generate_tests("convert json to csv", config)
    assert out["tests"][0]["name"] == "t1"


def test_validate_output_pass_rate(config, mock_llm):
    mock_llm({"results": [
        {"name": "t1", "passed": True, "reason": "ok"},
        {"name": "t2", "passed": False, "reason": "missing header"},
    ]})
    tests = [{"name": "t1", "criterion": "x"}, {"name": "t2", "criterion": "y"}]
    out = tier_b_tdd.validate_output("p", "the output", tests, cycle=1, config=config)
    assert out["passed_tests"] == 1 and out["total_tests"] == 2
    assert out["pass_rate"] == 0.5
    assert len(out["failed"]) == 1


def test_validate_uses_deep_model_on_final_cycle(config, mock_llm):
    captured = {}

    def responder(model, system, user):
        captured["model"] = model
        return {"results": [{"name": "t1", "passed": True}]}

    mock_llm(responder)
    tier_b_tdd.validate_output("p", "o", [{"name": "t1", "criterion": "x"}],
                               cycle=config.tdd_max_cycles, config=config)
    assert captured["model"] == config.tier_b_deep_model
