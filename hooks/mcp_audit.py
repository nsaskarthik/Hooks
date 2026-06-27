"""Category 1 - MCP audit logging.

MCP tools are deterministic code, so their output is not validated. PostToolUse on
``mcp__*`` simply records a structured audit entry with the requested fields:
timestamp, request, model_name, tool_called, response, response_status,
execution_duration_ms.

Note: the live Claude Code ``PostToolUse`` payload does not currently carry
``model`` or ``duration_ms``. Those two keys are kept for schema compatibility with
the spec but are populated only when the payload provides them (otherwise ``""``/0);
downstream consumers should treat ``model_name`` / ``execution_duration_ms`` as
best-effort, not guaranteed.
"""

from typing import Any


def build_audit_record(input_data: dict[str, Any]) -> dict[str, Any]:
    """Build the Category 1 audit record from a PostToolUse event payload."""
    tool_output = input_data.get("tool_output")
    # Only a present output with no explicit error field is "success". Detect an
    # error by field *presence* (not truthiness) so {"error": ""} still counts.
    has_output = "tool_output" in input_data
    has_error = "error" in input_data and input_data["error"] is not None
    if isinstance(tool_output, dict):
        has_error = has_error or (
            "error" in tool_output and tool_output["error"] is not None
        )
    status = "success" if has_output and not has_error else "error"

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
