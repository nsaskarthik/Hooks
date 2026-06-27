"""Category 1 - MCP audit logging.

MCP tools are deterministic code, so their output is not validated. PostToolUse on
``mcp__*`` simply records a structured audit entry with the requested fields:
timestamp, request, model_name, tool_called, response, response_status,
execution_duration_ms.
"""

from typing import Any


def build_audit_record(input_data: dict[str, Any]) -> dict[str, Any]:
    """Build the Category 1 audit record from a PostToolUse event payload."""
    tool_output = input_data.get("tool_output")
    # Heuristic status: a present, non-error output is "success".
    status = "success"
    if isinstance(tool_output, dict) and tool_output.get("error"):
        status = "error"
    if input_data.get("error"):
        status = "error"

    return {
        "hook_name": "mcp_audit",
        "category": 1,
        "status": status,
        "request": input_data.get("tool_input", {}),
        "model_name": input_data.get("model", ""),
        "tool_called": input_data.get("tool_name", ""),
        "response": tool_output,
        "response_status": status,
        "execution_duration_ms": input_data.get("duration_ms", 0),
        "session_id": input_data.get("session_id", ""),
    }
