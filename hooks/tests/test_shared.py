"""Tests for shared infrastructure: config flags, logger, JSON parsing, models."""

import builtins
import json

import pytest

from hooks.shared import llm_client, models_registry
from hooks.shared.config import get_config
from hooks.shared.errors import LLMError
from hooks.shared.logger import HookLogger


def test_default_flags(config):
    # Tier A rewrite on by default; Tier B TDD off by default.
    assert config.always_rewrite is True
    assert config.enable_tdd is False
    assert config.tdd_max_cycles == 3
    assert config.tdd_pass_threshold == 0.95


def test_env_overrides_flags(monkeypatch):
    from hooks.shared.config import get_config

    monkeypatch.setenv("ENABLE_TDD", "true")
    monkeypatch.setenv("ENABLE_PROMPT_REWRITE", "false")
    cfg = get_config(reload=True)  # reload so env overrides are re-read, not cached
    assert cfg.enable_tdd is True
    assert cfg.always_rewrite is False


def test_logger_appends_jsonl(tmp_path):
    logger = HookLogger(tmp_path)
    logger.log("demo", {"category": 1, "status": "pass"})
    logger.log("demo", {"category": 1, "status": "fail"})
    lines = (tmp_path / "demo.log.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert rec["hook_name"] == "demo" and rec["status"] == "pass" and "timestamp" in rec


def test_parse_json_object_variants():
    assert llm_client.parse_json_object('{"a": 1}')["a"] == 1
    assert llm_client.parse_json_object('```json\n{"a": 2}\n```')["a"] == 2
    assert llm_client.parse_json_object('Here you go: {"a": 3}. Done.')["a"] == 3


def test_model_cost():
    cost = models_registry.get_model_cost(models_registry.HAIKU, 1_000_000, 0)
    assert cost == 1.00  # Claude Haiku 4.5 input rate


# --- LLM backend selection / availability ---

def test_default_backend_is_agent_sdk(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    assert get_config(reload=True).llm_backend == "agent_sdk"


def test_llm_available_api_backend(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "api")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert get_config(reload=True).llm_available is True
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert get_config(reload=True).llm_available is False


def test_llm_available_agent_sdk_with_token(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "agent_sdk")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    assert get_config(reload=True).llm_available is True


def test_complete_api_requires_key():
    with pytest.raises(LLMError):
        llm_client.complete("m", "s", "u", backend="api", api_key=None)


def test_complete_rejects_unknown_backend():
    with pytest.raises(LLMError):
        llm_client.complete("m", "s", "u", backend="bogus")


def test_parse_json_object_rejects_non_dict():
    with pytest.raises(LLMError):
        llm_client.parse_json_object("[1, 2, 3]")


def test_redact_masks_secrets():
    from hooks.shared.redact import redact
    assert "***" in redact("--password=hunter2")
    assert "hunter2" not in redact("--password=hunter2")
    assert redact("export TOKEN=abc123").endswith("***")
    assert "AKIA" + "*" * 16 == redact("AKIAIOSFODNN7EXAMPLE")[:20]
    assert redact("") == ""           # falsy input is safe
    assert redact("plain text") == "plain text"   # nothing to mask


def test_usage_int_handles_dict_object_and_none():
    # Token usage may arrive as a dict, an SDK object, or be missing entirely;
    # extraction must never raise (it must stay inside the LLMError contract).
    class _Usage:
        input_tokens = 7

    assert llm_client._usage_int({"input_tokens": 5}, "input_tokens") == 5
    assert llm_client._usage_int(_Usage(), "input_tokens") == 7
    assert llm_client._usage_int(None, "input_tokens") == 0
    assert llm_client._usage_int({"input_tokens": None}, "input_tokens") == 0
    assert llm_client._usage_int({"input_tokens": "bad"}, "input_tokens") == 0


def test_complete_agent_sdk_missing_pkg_raises(monkeypatch):
    """When claude_agent_sdk isn't importable, complete() raises LLMError (callers fail open)."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "claude_agent_sdk":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(LLMError):
        llm_client.complete("m", "s", "u", backend="agent_sdk")
