"""Shared Tier A/B pipeline used by both prompt hooks.

UserPromptSubmit and UserPromptExpansion differ only in how they EMIT the result
(additionalContext vs the expandedPrompt rewrite). The work before that — refine
the prompt, decide whether to apply it, and (when flagged) generate + store TDD
criteria — is identical and lives here so it is written and tested once.
"""

from typing import Any

from . import tier_a_refine, tier_b_tdd
from ..context_manager.context import ContextStore


def refine_and_prepare(prompt: str, session_id: str, config, logger, event_name: str) -> dict[str, Any]:
    """Refine ``prompt`` and, when enabled, generate/store TDD criteria.

    Returns ``{applied, refined, refinement}`` where ``applied`` says whether the
    rewrite should be used. Never raises — the caller emits based on the result.
    """
    result: dict[str, Any] = {"applied": False, "refined": prompt, "refinement": None}

    if config.always_rewrite:
        refinement = tier_a_refine.refine_prompt(prompt, config)
        logger.log("tier_a_refine", {**refinement, "event": event_name})
        result["refinement"] = refinement
        if tier_a_refine.should_apply(refinement, config):
            result["applied"] = True
            result["refined"] = refinement["refined_prompt"]

    if config.enable_tdd and config.has_api_key:
        _generate_and_store_tdd(result["refined"], session_id, config, logger)

    return result


def _generate_and_store_tdd(prompt: str, session_id: str, config, logger) -> None:
    try:
        gen = tier_b_tdd.generate_tests(prompt, config)
        logger.log("tier_b_generate", gen)
        ContextStore(config.state_dir).save(
            f"tdd_{session_id}",
            {"prompt": prompt, "tests": gen["tests"], "cycle": 0},
        )
    except Exception as e:  # noqa: BLE001 - TDD must never break the prompt
        logger.log("tier_b_generate", {"category": 2, "status": "error", "reason": str(e)})
