"""Test fixtures: make the package importable and mock the LLM + config."""

import sys
from pathlib import Path

import pytest

# Repo root on sys.path so `import hooks_v2...` works under pytest.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from hooks_v2.shared.config import HookConfig  # noqa: E402


@pytest.fixture
def config(tmp_path, monkeypatch):
    """A HookConfig with a fake API key and temp log/state dirs."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HOOKS_LOG_DIR", str(tmp_path / "logs"))
    cfg = HookConfig()
    cfg.log_dir = tmp_path / "logs"
    cfg.state_dir = tmp_path / "logs" / "state"
    return cfg


@pytest.fixture
def mock_llm(monkeypatch):
    """Replace llm_client.complete with a scripted responder.

    Usage: ``mock_llm({"refined_prompt": ...})`` returns that JSON as text.
    Pass a callable to vary the response by (model, system, user).
    """
    from hooks_v2.shared import llm_client

    def _install(response):
        def fake_complete(model, system, user, **kwargs):
            payload = response(model, system, user) if callable(response) else response
            import json as _json
            text = payload if isinstance(payload, str) else _json.dumps(payload)
            return {"text": text, "input_tokens": 10, "output_tokens": 10, "model": model}

        monkeypatch.setattr(llm_client, "complete", fake_complete)

    return _install
