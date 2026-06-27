# MASTER PROMPT v2.0: Claude Code CLI Hooks System

**Version:** 2.0  
**Date:** June 27, 2026  
**Target:** Ubuntu 24.04, Python ≥3.12 (Single User, Local)  
**Status:** Ready for Implementation

---

## EXECUTIVE SUMMARY

Build a three-category hook system for Claude Code CLI that handles **input → processing → output** for all workflows, tasks, plugins, subagents, skills, and MCP servers.

**Three Categories:**
1. **Category 1:** Pure deterministic logic (no LLM)
2. **Category 2:** LLM-enhanced with validation & intelligent retry
3. **Category 3:** Interactive info gathering (no hallucination)

**Key Points:**
- Single-machine execution (your local Ubuntu 24.04)
- All logs in **human-readable JSON** format (easy to inspect)
- No distributed systems, no external services
- Three clear script modules: `lifecycle_events/`, `context_manager/`, `shared/`

---

## FILE STRUCTURE

```
hooks/
├── lifecycle_events/              # Lifecycle event handlers
│   ├── __init__.py
│   ├── pre_tool_use.py           # Runs BEFORE any tool execution
│   ├── post_tool_use.py          # Runs AFTER any tool execution
│   ├── permission_request.py     # Runs on permission dialog
│   ├── session_start.py          # Session initialization
│   ├── session_end.py            # Session cleanup
│   └── stop.py                   # When Claude finishes responding
│
├── context_manager/               # Execution context & state tracking
│   ├── __init__.py
│   └── context.py                # Track session, turn, tool execution
│
├── shared/                        # Shared utilities (all modules use these)
│   ├── __init__.py
│   ├── config.py                 # Load config from YAML/env
│   ├── logger.py                 # Structured JSON logging
│   ├── errors.py                 # Custom exceptions
│   └── models_registry.py        # Model IDs (Haiku, Sonnet, Opus)
│
├── tests/
│   ├── __init__.py
│   ├── test_lifecycle.py
│   ├── test_context.py
│   └── test_shared.py
│
├── config.yaml                    # Configuration
├── requirements.txt               # Dependencies
└── README.md                      # Setup instructions
```

---

## PART 1: CATEGORY 1 - DETERMINISTIC HOOKS

**Definition:** Pure Python logic. No LLM calls. No external I/O. Deterministic input → output.

**Purpose:** Validate, transform, or filter data before/after tool execution.

**Examples:**
- JSON schema validation
- File format checking
- Data sanitization (remove secrets, normalize paths)
- Git operations (validate branch names)
- Encoding checks (UTF-8 validation)

### Requirements
1. **Fast:** Complete in <100ms
2. **Reliable:** 100% pass/fail clarity
3. **Error Logs:** Always log why failure occurred
4. **No Dependencies:** No API calls, no network latency

### Output Schema
```json
{
  "status": "pass | fail",
  "hook_name": "json_validator",
  "category": 1,
  "input_hash": "sha256_hash",
  "error": null | "error message",
  "duration_ms": 45,
  "timestamp": "2026-06-27T14:30:45.123Z",
  "metadata": {
    "validation_rules_applied": 3,
    "fields_checked": 12
  }
}
```

### Implementation Example

**File:** `hooks/lifecycle_events/pre_tool_use.py`

```python
"""PreToolUse validation - runs before ANY tool execution"""

import json
import time
from typing import Dict, Any
from shared.logger import get_logger
from shared.errors import ValidationError

logger = get_logger(__name__)

def validate_bash_command(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Validate Bash commands before execution"""
    start_time = time.time()
    
    command = tool_input.get("command", "")
    
    # Check for dangerous patterns
    dangerous_patterns = ["rm -rf", "dd if=", "mkfs", ":(){ :|:& };:"]
    
    for pattern in dangerous_patterns:
        if pattern in command:
            return {
                "status": "fail",
                "hook_name": "validate_bash",
                "category": 1,
                "error": f"Dangerous command blocked: contains '{pattern}'",
                "duration_ms": int((time.time() - start_time) * 1000),
                "timestamp": time.time(),
                "metadata": {"command_length": len(command)}
            }
    
    # Check for valid command syntax
    if not command.strip():
        return {
            "status": "fail",
            "hook_name": "validate_bash",
            "category": 1,
            "error": "Empty command",
            "duration_ms": int((time.time() - start_time) * 1000),
            "timestamp": time.time()
        }
    
    return {
        "status": "pass",
        "hook_name": "validate_bash",
        "category": 1,
        "duration_ms": int((time.time() - start_time) * 1000),
        "timestamp": time.time(),
        "metadata": {"command_length": len(command)}
    }


def validate_json_file(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Validate JSON file format before write"""
    start_time = time.time()
    
    content = tool_input.get("content", "")
    
    try:
        json.loads(content)
        return {
            "status": "pass",
            "hook_name": "validate_json",
            "category": 1,
            "duration_ms": int((time.time() - start_time) * 1000),
            "timestamp": time.time(),
            "metadata": {"file_size_bytes": len(content)}
        }
    except json.JSONDecodeError as e:
        return {
            "status": "fail",
            "hook_name": "validate_json",
            "category": 1,
            "error": f"Invalid JSON: {str(e)}",
            "duration_ms": int((time.time() - start_time) * 1000),
            "timestamp": time.time()
        }
```

---

## PART 2: CATEGORY 2 - LLM-ENHANCED HOOKS

### Tier A: PROMPT REFINEMENT (Haiku Model)

**Purpose:** Clarify raw/ambiguous user prompts without changing intent.

**Model:** `claude-3-5-haiku-20241022` (cost-light)

**When to Use:**
- User prompt is vague: "fix the thing"
- Acronyms or shorthand: "CORS issue in the API"
- Ambiguous scope: "update the config"

### Output Schema
```json
{
  "status": "success | ambiguous",
  "hook_name": "prompt_refinement",
  "category": 2,
  "tier": "A",
  "original_prompt": "fix the thing",
  "refined_prompt": "Fix the authentication timeout issue in the login endpoint by increasing the session TTL from 30 minutes to 1 hour",
  "confidence_score": 0.92,
  "flagged_issues": [],
  "model_used": "claude-3-5-haiku-20241022",
  "input_tokens": 156,
  "output_tokens": 89,
  "duration_ms": 823,
  "timestamp": "2026-06-27T14:31:00.456Z"
}
```

### Implementation Example

**File:** `hooks/llm_enhanced/prompt_refinement.py`

```python
"""Tier A - Prompt refinement using Haiku"""

import time
import json
from anthropic import Anthropic
from shared.config import get_config
from shared.logger import get_logger
from shared.models_registry import HAIKU

logger = get_logger(__name__)
config = get_config()

def refine_prompt(original_prompt: str) -> dict:
    """Refine user prompt for clarity using Haiku"""
    start_time = time.time()
    
    client = Anthropic(api_key=config.anthropic_api_key)
    
    system_prompt = """You are a prompt clarification assistant. Your job is to take vague or ambiguous user prompts and make them more specific and clear, WITHOUT changing the core intent.

Rules:
1. Keep the same goal and context
2. Add specific details if they're missing
3. Clarify ambiguous terms
4. If you cannot clarify without guessing, return status "ambiguous"
5. Return JSON with: refined_prompt, confidence_score (0.0-1.0), flagged_issues (array)"""
    
    response = client.messages.create(
        model=HAIKU,
        max_tokens=500,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"Clarify this prompt: {original_prompt}"
            }
        ]
    )
    
    # Parse Claude's response
    try:
        response_text = response.content[0].text
        refined_data = json.loads(response_text)
        
        return {
            "status": refined_data.get("status", "success"),
            "hook_name": "prompt_refinement",
            "category": 2,
            "tier": "A",
            "original_prompt": original_prompt,
            "refined_prompt": refined_data.get("refined_prompt", original_prompt),
            "confidence_score": refined_data.get("confidence_score", 0.5),
            "flagged_issues": refined_data.get("flagged_issues", []),
            "model_used": HAIKU,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "duration_ms": int((time.time() - start_time) * 1000),
            "timestamp": time.time()
        }
    
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error(f"Failed to parse Haiku response: {str(e)}")
        return {
            "status": "ambiguous",
            "hook_name": "prompt_refinement",
            "category": 2,
            "tier": "A",
            "original_prompt": original_prompt,
            "refined_prompt": original_prompt,
            "confidence_score": 0.0,
            "flagged_issues": [f"Parse error: {str(e)}"],
            "model_used": HAIKU,
            "duration_ms": int((time.time() - start_time) * 1000),
            "timestamp": time.time()
        }
```

### Tier B: TDD VALIDATION WITH SMART RETRY (Sonnet → Opus)

**Purpose:** Generate test cases → execute → validate → fix if needed (max 3 cycles)

**Models:**
- Cycles 1-2: `claude-sonnet-4-6-20250514`
- Cycle 3: `claude-opus-4-8-20250514` (deep analysis)

**Workflow:**
```
1. PRE: Sonnet generates 3-5 test cases
2. EXECUTE: Run task with test inputs
3. VALIDATE: Check pass rate
4. RETRY (max 3 cycles): If <95% pass, analyze + fix + re-run
5. RESULT: Complete (≥95%) OR requires-review
```

### Output Schema
```json
{
  "status": "complete | requires-review | timeout",
  "hook_name": "tdd_validation",
  "category": 2,
  "tier": "B",
  "task_input": {"data": [1, 2, 3]},
  "generated_test_cases": [
    {
      "name": "test_valid_input",
      "description": "Convert valid JSON array to CSV",
      "input": {"data": [1, 2, 3]},
      "expected_output": "1,2,3"
    }
  ],
  "retry_cycles": [
    {
      "cycle": 1,
      "model_used": "claude-sonnet-4-6-20250514",
      "analysis": "Test failed because output format was JSON instead of CSV",
      "action_taken": "Added CSV formatting to conversion logic",
      "pass_rate": 0.80,
      "passed_tests": 4,
      "total_tests": 5,
      "duration_ms": 1200,
      "timestamp": "2026-06-27T14:31:30.000Z"
    }
  ],
  "final_output": "1,2,3",
  "final_pass_rate": 1.0,
  "total_tokens_used": 5400,
  "total_duration_ms": 4120,
  "timestamp": "2026-06-27T14:31:35.000Z"
}
```

### Tier C: SKILL OUTPUT VALIDATION (Sonnet)

**Purpose:** Validate skill/plugin output against schema + semantics

**When to Use:**
- After skill execution
- Verify output structure is correct
- Detect hallucinations

### Output Schema
```json
{
  "status": "valid | invalid_schema | invalid_semantics",
  "hook_name": "skill_validation",
  "category": 2,
  "tier": "C",
  "skill_name": "summarize_text",
  "skill_output": {
    "summary": "This is a summary...",
    "word_count": 150
  },
  "validation_result": {
    "schema_valid": true,
    "semantic_valid": true,
    "errors": [],
    "warnings": []
  },
  "model_used": "claude-sonnet-4-6-20250514",
  "duration_ms": 650,
  "cached": false,
  "timestamp": "2026-06-27T14:31:50.000Z"
}
```

---

## PART 3: CATEGORY 3 - INTERACTIVE HOOKS

**Purpose:** Ask for missing critical info before processing. Never hallucinate.

**When to Use:**
- Required fields missing
- Ambiguous context
- Need user confirmation

### Output Schema
```json
{
  "status": "info_gathered | user_declined",
  "hook_name": "clarify_info",
  "category": 3,
  "missing_fields": ["endpoint_url", "auth_method", "test_data"],
  "user_responses": {
    "endpoint_url": "https://api.example.com/users",
    "auth_method": "Bearer token",
    "test_data": "{\"name\": \"John\"}"
  },
  "complete_context": {
    "endpoint_url": "https://api.example.com/users",
    "auth_method": "Bearer token",
    "test_data": "{\"name\": \"John\"}",
    "expected_status": 200
  },
  "timestamp": "2026-06-27T14:32:00.000Z"
}
```

### Implementation Example

**File:** `hooks/interactive/clarify.py`

```python
"""Category 3 - Interactive info gathering"""

import time
from typing import Dict, List, Any
from shared.logger import get_logger

logger = get_logger(__name__)

def ask_for_missing_info(required_fields: List[str]) -> Dict[str, Any]:
    """Ask user for missing critical info"""
    start_time = time.time()
    
    print("\n⚠️  Missing required information:")
    print("=" * 50)
    
    user_responses = {}
    
    for field in required_fields:
        while True:
            user_input = input(f"  {field}: ").strip()
            
            if not user_input:
                print(f"    ❌ '{field}' cannot be empty. Please provide a value.")
                continue
            
            # Basic validation
            if field == "endpoint_url" and not (user_input.startswith("http://") or user_input.startswith("https://")):
                print(f"    ❌ Invalid URL. Must start with http:// or https://")
                continue
            
            user_responses[field] = user_input
            print(f"    ✅ {field} set")
            break
    
    print("=" * 50)
    
    return {
        "status": "info_gathered",
        "hook_name": "clarify_info",
        "category": 3,
        "missing_fields": required_fields,
        "user_responses": user_responses,
        "complete_context": user_responses,
        "duration_ms": int((time.time() - start_time) * 1000),
        "timestamp": time.time()
    }
```

---

## PART 4: SHARED INFRASTRUCTURE

### 4.1 Context Manager

**File:** `hooks/context_manager/context.py`

```python
"""Track execution context across hook lifecycle"""

import time
from typing import Dict, Any, Optional

class ExecutionContext:
    """Manages session/turn/tool execution state"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.turn_id: Optional[str] = None
        self.current_tool: Optional[str] = None
        self.tool_input: Optional[Dict] = None
        self.tool_output: Optional[Dict] = None
        self.permission_mode: Optional[str] = None
        self.start_time = time.time()
        self.current_tool_start_time: Optional[float] = None
    
    def start_tool(self, tool_name: str, tool_input: Dict):
        """PreToolUse: Track tool execution start"""
        self.current_tool = tool_name
        self.tool_input = tool_input
        self.current_tool_start_time = time.time()
    
    def complete_tool(self, output: Dict):
        """PostToolUse: Track tool execution end"""
        self.tool_output = output
    
    def get_duration_ms(self) -> int:
        """Get tool execution duration in ms"""
        if self.current_tool_start_time:
            return int((time.time() - self.current_tool_start_time) * 1000)
        return 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Export context for logging"""
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "current_tool": self.current_tool,
            "tool_input_keys": list(self.tool_input.keys()) if self.tool_input else None,
            "permission_mode": self.permission_mode,
            "session_duration_ms": int((time.time() - self.start_time) * 1000),
            "tool_duration_ms": self.get_duration_ms()
        }
```

### 4.2 Config Loader

**File:** `hooks/shared/config.py`

```python
"""Load configuration from YAML and environment"""

import os
from pathlib import Path
import yaml
from typing import Optional

class HookConfig:
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.getenv("HOOKS_CONFIG_PATH", "./config.yaml")
        
        self.config_path = Path(config_path)
        self.data = {}
        
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                self.data = yaml.safe_load(f) or {}
        
        # Override with environment variables
        self.anthropic_api_key = os.getenv(
            "ANTHROPIC_API_KEY",
            self.data.get("anthropic", {}).get("api_key")
        )
        
        self.enable_tier_a = os.getenv(
            "ENABLE_TIER_A",
            str(self.data.get("gates", {}).get("enable_tier_a", False))
        ).lower() == "true"
        
        self.log_file = os.getenv(
            "HOOKS_LOG_FILE",
            self.data.get("logging", {}).get("file", "/tmp/hooks.log")
        )
        
        self.timeout_seconds = int(os.getenv(
            "HOOKS_TIMEOUT",
            self.data.get("anthropic", {}).get("timeout_seconds", 240)
        ))

def get_config() -> HookConfig:
    """Get global config instance"""
    if not hasattr(get_config, "_instance"):
        get_config._instance = HookConfig()
    return get_config._instance
```

### 4.3 Logger (Human-Readable JSON)

**File:** `hooks/shared/logger.py`

```python
"""Structured JSON logging to file"""

import json
import time
from pathlib import Path
from typing import Any, Dict
from datetime import datetime

class HookLogger:
    def __init__(self, log_file: str = "/tmp/hooks.log"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def log(self, hook_name: str, event_data: Dict[str, Any]):
        """Write one structured log entry"""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "hook_name": hook_name,
            **event_data
        }
        
        # Pretty-print for readability
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry, indent=2) + "\n\n")
    
    def log_hook_execution(
        self,
        hook_name: str,
        category: int,
        status: str,
        duration_ms: int,
        error: str = None,
        metadata: Dict = None
    ):
        """Log hook execution result"""
        self.log(hook_name, {
            "category": category,
            "status": status,
            "duration_ms": duration_ms,
            "error": error,
            "metadata": metadata or {}
        })

def get_logger(name: str = "hooks") -> HookLogger:
    """Get logger instance"""
    if not hasattr(get_logger, "_instance"):
        from shared.config import get_config
        config = get_config()
        get_logger._instance = HookLogger(config.log_file)
    return get_logger._instance
```

### 4.4 Models Registry

**File:** `hooks/shared/models_registry.py`

```python
"""Model version management"""

# Latest Claude models (as of June 2026)
HAIKU = "claude-3-5-haiku-20241022"
SONNET = "claude-sonnet-4-6-20250514"
OPUS = "claude-opus-4-8-20250514"

# Model costs (input/output tokens per million)
COSTS = {
    HAIKU: {"input": 0.80, "output": 4.00},
    SONNET: {"input": 3.00, "output": 15.00},
    OPUS: {"input": 5.00, "output": 25.00},
}

def get_model_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate API cost for a model call"""
    if model not in COSTS:
        return 0.0
    
    cost_data = COSTS[model]
    input_cost = (input_tokens / 1_000_000) * cost_data["input"]
    output_cost = (output_tokens / 1_000_000) * cost_data["output"]
    
    return round(input_cost + output_cost, 6)
```

---

## PART 5: CONFIGURATION

**File:** `config.yaml`

```yaml
# Anthropic API
anthropic:
  api_key: ${ANTHROPIC_API_KEY}
  timeout_seconds: 240  # 4 minutes max for Tier B

# Model selection
models:
  tier_a_prompt_refinement: "claude-3-5-haiku-20241022"
  tier_b_generation: "claude-sonnet-4-6-20250514"
  tier_b_deep_analysis: "claude-opus-4-8-20250514"
  tier_c_validation: "claude-sonnet-4-6-20250514"

# Feature gates (user enables)
gates:
  enable_tier_a: false
  enable_tier_b: false
  enable_tier_c: false
  tier_b_max_cycles: 3
  tier_b_pass_rate_threshold: 0.95

# Logging
logging:
  level: "INFO"
  file: "/tmp/hooks.log"
  format: "json"  # Human-readable pretty JSON

# Notifications (future)
notifications:
  enabled: false
  type: "file"  # Only JSON file logging
  log_file: "/tmp/hook_notifications.json"
```

---

## PART 6: DEPENDENCIES

**File:** `requirements.txt`

```
anthropic>=0.25.0
pydantic>=2.0
pyyaml>=6.0
loguru>=0.7.0
pytest>=7.0
```

---


## PART 7: EXAMPLE LOG OUTPUT

```json
{
  "timestamp": "2026-06-27T14:31:15.456Z",
  "hook_name": "validate_bash",
  "category": 1,
  "status": "pass",
  "duration_ms": 45,
  "error": null,
  "metadata": {
    "command_length": 23,
    "validation_rules_applied": 3
  }
}

{
  "timestamp": "2026-06-27T14:31:20.789Z",
  "hook_name": "prompt_refinement",
  "category": 2,
  "tier": "A",
  "status": "success",
  "original_prompt": "fix the thing",
  "refined_prompt": "Fix the authentication timeout issue in the login endpoint",
  "confidence_score": 0.92,
  "duration_ms": 823,
  "input_tokens": 156,
  "output_tokens": 89
}

{
  "timestamp": "2026-06-27T14:31:30.123Z",
  "hook_name": "clarify_info",
  "category": 3,
  "status": "info_gathered",
  "missing_fields": [
    "endpoint_url",
    "auth_method"
  ],
  "user_responses": {
    "endpoint_url": "https://api.example.com",
    "auth_method": "Bearer token"
  },
  "duration_ms": 5400
}
```

---

## PART 8: SUCCESS CRITERIA

| Item | Target |
|------|--------|
| Category 1 execution time | <100ms |
| Tier A refinement time | <1s |
| Tier A confidence score | ≥0.85 |
| Logging coverage | 100% of executions |
| Log readability | Human-readable JSON |
| Setup time | <5 minutes |

---

## END OF MASTER PROMPT v2.0

**This is the complete specification.**

All implementation details are here. No distributed systems. No external services. Single-machine, human-readable logging.
