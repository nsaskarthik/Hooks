# hooks_v2 — Prompt-rewrite + TDD validation hooks

A Category-2 (LLM-enhanced) hook system for Claude Code, built to the
`Requirment.md` v2.0 spec. It refines **the user's input prompt** as it is
submitted, audits **MCP** tool calls, and optionally validates the final response
against generated acceptance criteria.

## What it does

| Event | Trigger | Action |
|-------|---------|--------|
| **UserPromptExpansion** | a slash command / skill (`/test ...`) expands | **Tier A** refine `expanded_prompt` -> **true rewrite** via `expandedPrompt` |
| **UserPromptSubmit** | a normal typed prompt is submitted | **Tier A** refine `text` -> inject corrected version as `additionalContext` (event cannot replace text) |
| **PostToolUse** `mcp__.*` | an MCP tool returns | **Category 1** audit log only |
| **Stop** | Claude finishes a turn | **Tier B** validate response vs criteria; `decision:block`->retry <=3 cycles *(flagged)* |

### Why these events (not PreToolUse on Skill/Agent)

Prompt typos originate in **the user's input**, so refinement happens where that
input enters. There is an important platform asymmetry:

- **UserPromptExpansion** (slash commands / skills) supports a real rewrite via the
  `expandedPrompt` output field — the corrected prompt replaces the expansion.
- **UserPromptSubmit** (normal prompts) **cannot** replace the prompt; it can only
  block or add context. So the corrected version is injected as `additionalContext`
  and Claude acts on it.

Subagents are intentionally not wrapped: they own their own hooks and run in their
own context, so a parent-side `Agent` PreToolUse is the wrong mechanism. Workflows
and Tasks don't support hooks at all.

- **Tier A — prompt rewrite (priority, always on).** The prompt is sent to Haiku,
  which fixes spelling/typos and ambiguity **while strictly preserving intent**.
  Always **fails open**: no API key or any error → the original prompt is untouched.
- **Tier B — TDD generation + validation (gated by `enable_tdd`, off by default).**
  The prompt hooks derive acceptance criteria from the refined prompt and store them
  by `session_id`; the `Stop` hook scores the final response and, below the 95% pass
  threshold, emits `{"decision":"block"}` so Claude continues (≤3 cycles; final cycle
  uses Opus; honours `stop_hook_active`).
- **MCP — Category 1 audit only.** Deterministic tools, so output is not validated.
  PostToolUse records `timestamp, request, model_name, tool_called, response,
  response_status, execution_duration_ms`.

## Layout

```text
hooks_v2/
├── lifecycle_events/   user_prompt_submit.py, user_prompt_expansion.py,
│                       post_tool_use.py, stop.py            (hook entry points)
├── category2/          tier_a_refine.py, tier_b_tdd.py      (LLM tiers)
├── category1/          mcp_audit.py                          (deterministic audit)
├── context_manager/    context.py                           (prompt->Stop TDD state)
├── shared/             config.py, logger.py, errors.py, models_registry.py, llm_client.py
├── hooks/hooks.json    plugin hook registration
├── .claude-plugin/plugin.json
├── settings.example.json   project-local (non-plugin) registration
├── config.yaml · requirements.txt · tests/
```

## Install

**As a plugin:** point a marketplace/plugin install at this directory; `hooks/hooks.json`
registers the hooks using `${CLAUDE_PLUGIN_ROOT}`.

**Project-local:** copy the `hooks` block from `settings.example.json` into your
`.claude/settings.json` (it references `${CLAUDE_PROJECT_DIR}/hooks_v2/...`).

Then:
```bash
pip install -r hooks_v2/requirements.txt   # anthropic, pyyaml, python-dotenv
export ANTHROPIC_API_KEY=...               # required for Tier A/B; without it, hooks no-op
```

## Configuration (`config.yaml` or env)

| Setting | Env | Default | Meaning |
|---------|-----|---------|---------|
| `gates.always_rewrite` | `ENABLE_PROMPT_REWRITE` | `true` | Tier A prompt rewrite |
| `gates.refine_confidence_threshold` | `REFINE_CONFIDENCE_THRESHOLD` | `0.30` | Apply the rewrite when intent-preservation confidence ≥ this |
| `gates.enable_tdd` | `ENABLE_TDD` | `false` | Tier B generation + validation/retry |
| `tdd.max_cycles` | `TDD_MAX_CYCLES` | `3` | Retry cap |
| `tdd.pass_rate_threshold` | `TDD_PASS_THRESHOLD` | `0.95` | Pass bar |

Models: Tier A `claude-haiku-4-5`; Tier B gen/validate `claude-sonnet-4-6`; final cycle `claude-opus-4-8`.

## Test

```bash
python3 -m pytest hooks_v2/tests -q
```
