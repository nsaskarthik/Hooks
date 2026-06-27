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

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.logger import get_logger   # noqa: E402
from hooks_v2.category2 import tier_b_tdd        # noqa: E402
from hooks_v2.context_manager.context import ContextStore, session_key  # noqa: E402


def _last_assistant_text(transcript_path: str) -> str:
    """Return the text of the most recent assistant message in the transcript."""
    if not transcript_path or not Path(transcript_path).exists():
        return ""
    last = ""
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                content = entry.get("message", {}).get("content", entry.get("content", ""))
                if isinstance(content, str):
                    last = content or last
                elif isinstance(content, list):
                    texts = [b.get("text", "") for b in content
                             if isinstance(b, dict) and b.get("type") == "text"]
                    if any(texts):
                        last = "\n".join(t for t in texts if t)
    except OSError:
        return last
    return last


def main() -> None:
    """Read the Stop event and run flagged Tier B validation of the response."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        if not config.enable_tdd or not config.has_api_key:
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
        output_text = _last_assistant_text(input_data.get("transcript_path", ""))
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
