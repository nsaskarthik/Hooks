"""Tests for shared infrastructure: config flags, logger, JSON parsing, models."""

import json

from hooks_v2.shared import llm_client, models_registry
from hooks_v2.shared.logger import HookLogger


def test_default_flags(config):
    # Tier A rewrite on by default; Tier B TDD off by default.
    assert config.always_rewrite is True
    assert config.enable_tdd is False
    assert config.tdd_max_cycles == 3
    assert config.tdd_pass_threshold == 0.95


def test_env_overrides_flags(monkeypatch):
    from hooks_v2.shared.config import get_config

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
