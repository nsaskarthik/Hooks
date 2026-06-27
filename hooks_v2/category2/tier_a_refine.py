"""Tier A - Prompt refinement (the priority feature).

Takes a raw instruction that may contain spelling mistakes, typos, or ambiguous
shorthand and returns a corrected, clearer version of the SAME instruction. The
model is held to strict rules: fix mechanics, preserve intent, never add scope.

Always fails open: if there is no API key or the model call fails, the original
prompt is returned unchanged with ``status="skipped"`` so a hook never breaks a
tool call just because refinement was unavailable.
"""

import time
from typing import Any

from ..shared import llm_client
from ..shared.errors import LLMError

SYSTEM_PROMPT = """You are a prompt-refinement assistant for a developer tool. \
You receive ONE instruction written by a developer. It may contain spelling \
mistakes, typos, grammatical errors, or ambiguous shorthand. Produce a corrected, \
clearer version of the SAME instruction.

STRICT RULES:
1. Preserve the original intent and scope EXACTLY. Do not add new requirements, \
assumptions, file names, libraries, or steps the user did not state.
2. Fix spelling, typos, grammar, and garbled words. Expand only unambiguous \
abbreviations (e.g. "fn" -> "function" only when obvious).
3. If a word is genuinely ambiguous and you cannot correct it confidently, leave \
it as-is, list it under "ambiguities", and lower your confidence. NEVER guess a \
meaning that could change intent.
4. Keep code, file paths, identifiers, commands, URLs, and quoted strings \
byte-for-byte UNLESS they are clearly a misspelled English word.
5. Be concise. Do not pad, explain, greet, or add commentary.
6. If the instruction is already clear and correct, return it unchanged with high \
confidence.

Return ONLY a JSON object, no prose:
{
  "refined_prompt": "<the corrected instruction>",
  "confidence_score": 0.0-1.0,        // how confident you preserved the intent
  "corrections": ["recieve -> receive", "..."],
  "ambiguities": ["words/phrases you could not safely resolve"]
}"""


def refine_prompt(original_prompt: str, config) -> dict[str, Any]:
    """Refine ``original_prompt``. Never raises; always returns a result dict."""
    start = time.time()

    base = {
        "hook_name": "tier_a_refine",
        "category": 2,
        "tier": "A",
        "original_prompt": original_prompt,
        "refined_prompt": original_prompt,
        "confidence_score": 0.0,
        "corrections": [],
        "ambiguities": [],
        "model_used": config.tier_a_model,
    }

    # Nothing meaningful to refine.
    if not original_prompt or not original_prompt.strip():
        base.update(status="skipped", reason="empty prompt",
                    duration_ms=int((time.time() - start) * 1000))
        return base

    if not config.has_api_key:
        base.update(status="skipped", reason="no api key",
                    duration_ms=int((time.time() - start) * 1000))
        return base

    try:
        result = llm_client.complete(
            config.tier_a_model,
            SYSTEM_PROMPT,
            f"Instruction to refine:\n{original_prompt}",
            max_tokens=1024,
            timeout=config.timeout_seconds,
            api_key=config.anthropic_api_key,
        )
        parsed = llm_client.parse_json_object(result["text"])
        refined = (parsed.get("refined_prompt") or original_prompt).strip()
        # parse_json_object guarantees JSON syntax, not field types. Coerce
        # defensively so a malformed payload can't crash the caller's fail-open path.
        try:
            confidence = float(parsed.get("confidence_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        corrections = parsed.get("corrections")
        ambiguities = parsed.get("ambiguities")
        base.update(
            status="success",
            refined_prompt=refined or original_prompt,
            confidence_score=confidence,
            corrections=corrections if isinstance(corrections, list) else [],
            ambiguities=ambiguities if isinstance(ambiguities, list) else [],
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            duration_ms=int((time.time() - start) * 1000),
        )
        return base
    except LLMError as e:
        # Fail open: keep the original prompt, record why.
        base.update(status="error", reason=str(e),
                    duration_ms=int((time.time() - start) * 1000))
        return base


def should_apply(refinement: dict[str, Any], config) -> bool:
    """Decide whether the refined prompt should replace the original.

    Applied whenever refinement succeeded, the text actually changed, and the
    model's intent-preservation confidence meets the (low) threshold. The
    threshold defaults low so the rewrite is kept in almost all cases.
    """
    if refinement.get("status") != "success":
        return False
    if refinement["refined_prompt"].strip() == refinement["original_prompt"].strip():
        return False
    return refinement.get("confidence_score", 0.0) >= config.refine_confidence_threshold
