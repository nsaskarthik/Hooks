#!/usr/bin/env python3
"""PostToolUse entry point - MCP audit logging only (Category 1).

MCP tools are deterministic code, so their output is not validated. This hook
records one structured audit entry per ``mcp__*`` call:
``timestamp, request, model_name, tool_called, response, response_status,
execution_duration_ms``. Every other tool is a no-op.

Always fails open: any error exits 0.
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT.parent))

from hooks.shared.config import get_config   # noqa: E402
from hooks.shared.logger import get_logger   # noqa: E402
from hooks import mcp_audit         # noqa: E402


def main() -> None:
    """Read the PostToolUse event and audit-log it when it's an MCP call."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    try:
        tool_name = input_data.get("tool_name", "")
        if tool_name.startswith("mcp__"):
            config = get_config()
            record = mcp_audit.build_audit_record(input_data)
            get_logger(config.log_dir).log("mcp_audit", record)
        sys.exit(0)
    except Exception:  # noqa: BLE001 - absolute fail-open guarantee
        sys.exit(0)


if __name__ == "__main__":
    main()
