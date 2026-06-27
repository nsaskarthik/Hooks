#!/usr/bin/env python3
"""UserPromptExpansion entry point - prompt rewrite for slash commands / skills.

Fires when a user-typed command like ``/deploy`` expands into a prompt. Unlike
UserPromptSubmit, this event CAN truly rewrite the text via the ``expandedPrompt``
output field, so Tier A's corrected prompt replaces the expansion before Claude
sees it.

Always fails open: any error exits 0 with no output, so the expansion is unaffected.
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
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        config = get_config()
        expanded = (input_data.get("expanded_prompt") or "").strip()
        session_id = input_data.get("session_id", "")
        if not expanded:
            sys.exit(0)

        result = pipeline.refine_and_prepare(
            expanded, session_id, config, get_logger(config.log_dir), "UserPromptExpansion"
        )

        if result["applied"]:
            # This event supports a true rewrite of the expanded prompt.
            print(json.dumps({"expandedPrompt": result["refined"]}))
        sys.exit(0)
    except Exception:  # noqa: BLE001 - absolute fail-open guarantee
        sys.exit(0)


if __name__ == "__main__":
    main()
