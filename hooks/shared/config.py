"""Load configuration from YAML and environment.

Precedence: environment variable > config.yaml > built-in default.

Key flags:
- always_rewrite      Tier A prompt refinement. ALWAYS ON by default (the priority feature).
- enable_tdd          Tier B TDD generation + validation. OFF by default (gated behind a flag).
"""

import os
from pathlib import Path

try:
    import yaml
except ImportError:  # pyyaml is optional; fall back to built-in defaults
    yaml = None

from . import models_registry as models


def _as_bool(value, default: bool) -> bool:
    """Coerce an env/YAML value to bool, returning ``default`` when unset."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class HookConfig:
    """Resolved configuration for the hook system."""

    def __init__(self, config_path: str | None = None):
        """Resolve config from env vars layered over the YAML file."""
        config_path = config_path or os.getenv(
            "HOOKS_CONFIG_PATH",
            str(Path(__file__).resolve().parent.parent / "config.yaml"),
        )
        self.config_path = Path(config_path)
        data: dict = {}
        if yaml is not None and self.config_path.exists():
            with open(self.config_path, "r") as f:
                loaded = yaml.safe_load(f)
            # A YAML file can parse to a list/scalar; only a mapping is usable.
            data = loaded if isinstance(loaded, dict) else {}

        gates = data.get("gates", {}) or {}
        tdd = data.get("tdd", {}) or {}
        logging_cfg = data.get("logging", {}) or {}
        models_cfg = data.get("models", {}) or {}
        anthropic_cfg = data.get("anthropic", {}) or {}
        notify_cfg = data.get("notify", {}) or {}

        # --- API ---
        self.anthropic_api_key = os.getenv(
            "ANTHROPIC_API_KEY", anthropic_cfg.get("api_key")
        )
        self.timeout_seconds = int(
            os.getenv("HOOKS_TIMEOUT", anthropic_cfg.get("timeout_seconds", 30))
        )

        # --- LLM backend ---
        # "agent_sdk" (default): call the Claude Agent SDK query(), authenticated
        #   by your Claude subscription (CLAUDE_CODE_OAUTH_TOKEN, or a logged-in
        #   `claude` CLI). No per-token API key required.
        # "api": call the Anthropic API directly (needs ANTHROPIC_API_KEY, billed
        #   at API rates).
        self.llm_backend = (
            os.getenv("LLM_BACKEND", anthropic_cfg.get("backend", "agent_sdk"))
            .strip()
            .lower()
        )

        # --- Feature gates ---
        # Tier A: prompt rewrite. Always on unless explicitly disabled.
        self.always_rewrite = _as_bool(
            os.getenv("ENABLE_PROMPT_REWRITE"), gates.get("always_rewrite", True)
        )
        # Tier B: TDD generation + test execution + validation. Off by default.
        self.enable_tdd = _as_bool(
            os.getenv("ENABLE_TDD"), gates.get("enable_tdd", False)
        )

        # Apply the refined prompt whenever refinement confidence is at least this
        # value. Kept low so the rewrite is applied in almost all cases (the user
        # wants the rewrite kept always); raise it to be more conservative.
        self.refine_confidence_threshold = float(
            os.getenv(
                "REFINE_CONFIDENCE_THRESHOLD",
                gates.get("refine_confidence_threshold", 0.30),
            )
        )

        # --- TDD parameters ---
        self.tdd_max_cycles = int(
            os.getenv("TDD_MAX_CYCLES", tdd.get("max_cycles", 3))
        )
        self.tdd_pass_threshold = float(
            os.getenv("TDD_PASS_THRESHOLD", tdd.get("pass_rate_threshold", 0.95))
        )
        self.tdd_num_tests = int(os.getenv("TDD_NUM_TESTS", tdd.get("num_tests", 4)))

        # --- Models ---
        self.tier_a_model = models_cfg.get("tier_a", models.TIER_A_MODEL)
        self.tier_b_gen_model = models_cfg.get("tier_b_gen", models.TIER_B_GEN_MODEL)
        self.tier_b_validate_model = models_cfg.get(
            "tier_b_validate", models.TIER_B_VALIDATE_MODEL
        )
        self.tier_b_deep_model = models_cfg.get("tier_b_deep", models.TIER_B_DEEP_MODEL)

        # --- Notifications ---
        # Channels the notifier fans out to. Override with NOTIFY_CHANNELS (comma
        # list). Default ["log"]; add "desktop"/"webhook"/"sms" as you enable them.
        self.notify_channels = notify_cfg.get("channels", ["log"]) or ["log"]

        # --- Paths ---
        root = Path(__file__).resolve().parent.parent
        log_value = os.getenv("HOOKS_LOG_DIR", logging_cfg.get("dir", "logs"))
        log_path = Path(log_value)
        # Resolve a relative dir against the hooks root, never the cwd, so logs
        # don't land wherever a hook happens to be invoked from.
        self.log_dir = log_path if log_path.is_absolute() else (root / log_path)
        self.state_dir = self.log_dir / "state"

    @property
    def has_api_key(self) -> bool:
        """True when an Anthropic API key is available."""
        return bool(self.anthropic_api_key)

    @property
    def llm_available(self) -> bool:
        """Whether an LLM call can be made under the configured backend.

        - ``api``: requires an Anthropic API key.
        - ``agent_sdk``: requires subscription auth — a CLAUDE_CODE_OAUTH_TOKEN,
          an API key the SDK can fall back to, or a logged-in ``claude`` CLI
          (``~/.claude/.credentials.json``).
        """
        if self.llm_backend == "api":
            return bool(self.anthropic_api_key)
        if os.getenv("CLAUDE_CODE_OAUTH_TOKEN") or self.anthropic_api_key:
            return True
        return (Path.home() / ".claude" / ".credentials.json").exists()


_INSTANCE: HookConfig | None = None


def get_config(reload: bool = False) -> HookConfig:
    """Return the process-wide config instance (cached)."""
    global _INSTANCE
    if _INSTANCE is None or reload:
        _INSTANCE = HookConfig()
    return _INSTANCE
