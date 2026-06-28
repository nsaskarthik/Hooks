#!/usr/bin/env python3
"""Stop entry point - flagged TDD validation of the final response.

Because subagents own their hooks and per-tool wrapping was dropped, Tier B
validation runs here: when Claude finishes a turn, the latest assistant message
is scored against the acceptance criteria generated from the (refined) prompt at
UserPromptSubmit / UserPromptExpansion. Below the pass threshold and under the
cycle cap, the hook returns ``{"decision":"block"}`` so Claude keeps working.

Gated entirely by ``enable_tdd`` (off by default). Honours ``stop_hook_active`` to
avoid the Stop-hook block-cap loop. Always fails open.
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT.parent))

from hooks.shared.config import get_config   # noqa: E402
from hooks.shared.logger import get_logger   # noqa: E402
from hooks.shared.events import audit_event   # noqa: E402
from hooks.shared.transcript import last_assistant_text  # noqa: E402
from hooks import tier_b_tdd        # noqa: E402
from hooks.context import ContextStore, session_key  # noqa: E402


def main() -> None:
    """Read the Stop event and run flagged Tier B validation of the response."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        # Always record the stop in the audit log, even when TDD is off.
        audit_event("Stop", input_data,
                    extra={"stop_hook_active": bool(input_data.get("stop_hook_active"))},
                    config=config)
        # Capture a memory entry every turn-end (deterministic, change-gated, fail-open),
        # independent of TDD. Commit only if MEMORY_AUTOCOMMIT is on.
        try:
            from hooks.shared import memory
            if memory.capture_entry(input_data):
                memory.commit_memory(input_data)
            memory.compact_if_needed()
        except Exception:  # noqa: BLE001 - memory must never break the hook
            pass
        if not config.enable_tdd or not config.llm_available:
            sys.exit(0)
        # Don't re-block once we've already asked Claude to continue.
        if input_data.get("stop_hook_active"):
            sys.exit(0)

        session_id = input_data.get("session_id", "")
        store = ContextStore(config.state_dir)
        key = session_key(session_id)
        state = store.load(key)
        if not state or not state.get("tests"):
            sys.exit(0)

        cycle = int(state.get("cycle", 0)) + 1
        # The documented Stop payload provides the final assistant message directly;
        # fall back to parsing the transcript only when it's absent.
        output_text = (input_data.get("assistant_message") or "").strip()
        if not output_text:
            output_text = last_assistant_text(input_data.get("transcript_path", ""))
        if not output_text:
            sys.exit(0)

        logger = get_logger(config.log_dir)
        try:
            validation = tier_b_tdd.validate_output(
                state["prompt"], output_text, state["tests"], cycle, config
            )
        except Exception as e:  # noqa: BLE001 - fail open
            logger.log("tier_b_validate", {"category": 2, "status": "error", "reason": str(e)})
            store.clear(key)
            sys.exit(0)

        logger.log("tier_b_validate", {**validation, "event": "Stop"})
        # Write a human-readable test-results summary (best-effort, never fatal).
        try:
            from hooks.shared import artifacts
            artifacts.write_test_results(
                validation, cwd=input_data.get("cwd", ""), session_id=session_id)
        except Exception:  # noqa: BLE001
            pass

        if validation["pass_rate"] >= config.tdd_pass_threshold or cycle >= config.tdd_max_cycles:
            store.clear(key)
            sys.exit(0)

        state["cycle"] = cycle
        store.save(key, state)
        # Build the retry message from trusted criterion names only. The model's
        # free-text "reason" is NOT echoed back, so a compromised validator can't
        # inject instructions into the next Claude turn.
        failed_names = "; ".join(
            str(r.get("name") or "unnamed criterion") for r in validation["failed"]
        )
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"Response failed {len(validation['failed'])}/{validation['total_tests']} "
                f"acceptance criteria (cycle {cycle}/{config.tdd_max_cycles}). "
                f"Address these criteria and continue: {failed_names}"
            ),
        }))
        sys.exit(0)
    except Exception:  # noqa: BLE001 - absolute fail-open guarantee
        sys.exit(0)


if __name__ == "__main__":
    main()
