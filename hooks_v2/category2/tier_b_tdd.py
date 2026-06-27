"""Tier B - TDD generation and output validation (gated behind the ``enable_tdd`` flag).

PreToolUse calls :func:`generate_tests` to derive acceptance criteria from the
(refined) prompt. PostToolUse calls :func:`validate_output` to score the tool's
output against those criteria. On the final cycle the deeper model is used.
"""

import time
from typing import Any

from ..shared import llm_client
from ..shared.errors import LLMError

GEN_SYSTEM = """You are a test designer. Given a developer instruction, produce a \
small set of concrete, checkable acceptance criteria ("tests") that the eventual \
output must satisfy. Each test is a single, objectively verifiable statement about \
the result - not about the process. Do not invent requirements beyond the \
instruction.

Return ONLY JSON:
{
  "tests": [
    {"name": "short_id", "criterion": "An objectively checkable statement"},
    ...
  ]
}"""

VALIDATE_SYSTEM = """You are a strict output validator. You are given a developer \
instruction, a list of acceptance criteria, and the actual output produced. For \
each criterion decide pass or fail based ONLY on the output. Be conservative: if \
the output does not clearly satisfy a criterion, mark it failed.

Return ONLY JSON:
{
  "results": [
    {"name": "short_id", "passed": true|false, "reason": "why"},
    ...
  ]
}"""


def generate_tests(prompt: str, config) -> dict[str, Any]:
    """Generate acceptance criteria for ``prompt``. Raises :class:`LLMError` on failure."""
    start = time.time()
    result = llm_client.complete(
        config.tier_b_gen_model,
        GEN_SYSTEM,
        f"Instruction:\n{prompt}\n\nProduce up to {config.tdd_num_tests} acceptance criteria.",
        max_tokens=1024,
        timeout=config.timeout_seconds,
        api_key=config.anthropic_api_key,
    )
    parsed = llm_client.parse_json_object(result["text"])
    tests = parsed.get("tests", []) or []
    return {
        "hook_name": "tier_b_generate",
        "category": 2,
        "tier": "B",
        "tests": tests,
        "model_used": config.tier_b_gen_model,
        "duration_ms": int((time.time() - start) * 1000),
    }


def validate_output(prompt: str, tool_output: str, tests: list[dict], cycle: int, config) -> dict[str, Any]:
    """Score ``tool_output`` against ``tests``.

    ``cycle`` is 1-based; the final cycle uses the deeper model. Raises
    :class:`LLMError` on failure (caller fails open).
    """
    start = time.time()
    model = config.tier_b_deep_model if cycle >= config.tdd_max_cycles else config.tier_b_validate_model
    criteria_text = "\n".join(f"- [{t.get('name')}] {t.get('criterion')}" for t in tests)
    user = (
        f"Instruction:\n{prompt}\n\n"
        f"Acceptance criteria:\n{criteria_text}\n\n"
        f"Actual output:\n{tool_output}"
    )
    result = llm_client.complete(
        model, VALIDATE_SYSTEM, user,
        max_tokens=1024, timeout=config.timeout_seconds, api_key=config.anthropic_api_key,
    )
    parsed = llm_client.parse_json_object(result["text"])
    results = parsed.get("results", []) or []
    total = len(results) or len(tests) or 1
    passed = sum(1 for r in results if r.get("passed"))
    pass_rate = round(passed / total, 4) if total else 0.0
    return {
        "hook_name": "tier_b_validate",
        "category": 2,
        "tier": "B",
        "cycle": cycle,
        "model_used": model,
        "results": results,
        "passed_tests": passed,
        "total_tests": total,
        "pass_rate": pass_rate,
        "failed": [r for r in results if not r.get("passed")],
        "duration_ms": int((time.time() - start) * 1000),
    }
