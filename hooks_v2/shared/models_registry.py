"""Model version management for the v2 hook system.

Uses current Claude model IDs (not the stale ones in Requirment.md).
Tier A (prompt refinement) -> Haiku (fast, cheap).
Tier B (TDD generation + validation) -> Sonnet, escalating to Opus on the final cycle.
"""

# Current Claude model IDs (June 2026)
HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-8"

# Per-tier defaults
TIER_A_MODEL = HAIKU              # prompt refinement
TIER_B_GEN_MODEL = SONNET         # test-case generation
TIER_B_VALIDATE_MODEL = SONNET    # validation, cycles 1-2
TIER_B_DEEP_MODEL = OPUS          # validation, final cycle (deep analysis)

# Approximate costs (USD per 1M tokens) for optional cost accounting in logs.
COSTS = {
    HAIKU: {"input": 0.80, "output": 4.00},
    SONNET: {"input": 3.00, "output": 15.00},
    OPUS: {"input": 5.00, "output": 25.00},
}


def get_model_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the approximate API cost for a single model call."""
    if model not in COSTS:
        return 0.0
    cost = COSTS[model]
    return round(
        (input_tokens / 1_000_000) * cost["input"]
        + (output_tokens / 1_000_000) * cost["output"],
        6,
    )
