"""Test fixtures: make the package importable and mock the LLM + config."""

import sys
from pathlib import Path

import pytest

# Repo root on sys.path so `import hooks...` works under pytest.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from hooks.shared.config import get_config  # noqa: E402

# Hook flags that must not leak in from the caller's environment.
_HOOK_ENV = ("ENABLE_TDD", "ENABLE_PROMPT_REWRITE", "REFINE_CONFIDENCE_THRESHOLD",
             "LLM_BACKEND", "CLAUDE_CODE_OAUTH_TOKEN")


@pytest.fixture(autouse=True)
def _no_side_writes(monkeypatch):
    """Disable on-disk artifact + memory writing for every test (set in os.environ so
    the subprocess hook tests inherit it too). test_artifacts.py / test_memory.py
    re-enable what they need after pointing dirs at temp paths."""
    monkeypatch.setenv("HOOK_ARTIFACTS", "false")
    monkeypatch.setenv("HOOK_MEMORY", "false")
    monkeypatch.setenv("MEMORY_AUTOCOMMIT", "false")


@pytest.fixture
def config(tmp_path, monkeypatch):
    """A fresh HookConfig on the API backend with a fake key and temp dirs.

    Rebuilt via the reload path with hook env vars cleared so the cached
    singleton and exported flags can't leak between tests. Pinned to the ``api``
    backend so availability keys off the fake key deterministically (the LLM call
    itself is mocked).
    """
    for key in _HOOK_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BACKEND", "api")
    monkeypatch.setenv("HOOKS_LOG_DIR", str(tmp_path / "logs"))
    cfg = get_config(reload=True)
    cfg.log_dir = tmp_path / "logs"
    cfg.state_dir = tmp_path / "logs" / "state"
    return cfg


@pytest.fixture
def mock_llm(monkeypatch):
    """Replace llm_client.complete with a scripted responder.

    Usage: ``mock_llm({"refined_prompt": ...})`` returns that JSON as text.
    Pass a callable to vary the response by (model, system, user).
    """
    from hooks.shared import llm_client

    def _install(response):
        def fake_complete(model, system, user, **kwargs):
            payload = response(model, system, user) if callable(response) else response
            import json as _json
            text = payload if isinstance(payload, str) else _json.dumps(payload)
            return {"text": text, "input_tokens": 10, "output_tokens": 10, "model": model}

        monkeypatch.setattr(llm_client, "complete", fake_complete)

    return _install
