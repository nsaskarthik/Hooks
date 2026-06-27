#!/usr/bin/env python3
"""UserPromptSubmit entry point - prompt rewrite for normal typed prompts.

Fires on every prompt submission. The platform does NOT allow replacing the
prompt text here (UserPromptSubmit can only block or add context), so Tier A
refines the prompt and the corrected version is injected as additional context so
Claude acts on the cleaned-up intent. Slash commands are skipped here - they are
handled by UserPromptExpansion, which CAN truly rewrite via expandedPrompt.

Always fails open: any error exits 0 with no output, so the prompt is unaffected.
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT.parent))

from hooks_v2.shared.config import get_config   # noqa: E402
from hooks_v2.shared.logger import get_logger   # noqa: E402
from hooks_v2.category2 import pipeline          # noqa: E402


def main() -> None:
    """Read the UserPromptSubmit event and inject a refined-prompt context note."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        text = (input_data.get("text") or "").strip()
        session_id = input_data.get("session_id", "")
        # Empty prompt, or a slash command (handled by UserPromptExpansion).
        if not text or text.startswith("/"):
            sys.exit(0)

        result = pipeline.refine_and_prepare(
            text, session_id, config, get_logger(config.log_dir), "UserPromptSubmit"
        )

        if result["applied"]:
            corrections = "; ".join(result["refinement"].get("corrections", []))
            context = (
                "The user's submitted prompt may contain typos or ambiguity. "
                "A corrected, intent-preserving version is:\n\n"
                f"{result['refined']}\n\n"
                + (f"(Corrections: {corrections}) " if corrections else "")
                + "Act on this corrected version."
            )
            # UserPromptSubmit cannot replace the prompt; add context instead.
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            }))
        sys.exit(0)
    except Exception:  # noqa: BLE001 - absolute fail-open guarantee
        sys.exit(0)


if __name__ == "__main__":
    main()
