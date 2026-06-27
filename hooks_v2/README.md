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

### Full lifecycle coverage + unified audit log

Beyond the LLM features above, v2 ships a hook for **every practical lifecycle
event** (ported and hardened from v1). They all write one structured record to a
single audit log — **`logs/audit.log.jsonl`** — so the whole session is greppable
in one place:

| Event | Script | What it does |
|-------|--------|--------------|
| `SessionStart` | `session_start.py` | Audit + inject git/branch + active-flags context |
| `SessionEnd` | `session_end.py` | Audit + sweep stale `tdd_*` state files |
| `Setup` | `setup.py` | Audit + project detection + persist `PROJECT_ROOT` |
| `PreToolUse` | `pre_tool_use.py` | **Block** dangerous commands (`rm -rf`, `dd`, fork bomb, `.env` access) via `permissionDecision: deny`; audit Bash |
| `PostToolUseFailure` | `post_tool_use_failure.py` | Audit tool failures (`status=error`) |
| `PermissionRequest` | `permission_request.py` | Audit; opt-in auto-allow read-only tools (`AUTO_ALLOW_READONLY=true`) |
| `Notification` | `notification.py` | Audit; opt-in desktop alert (`NOTIFY_DESKTOP=true`) |
| `SubagentStart` / `SubagentStop` | `subagent_start.py` / `subagent_stop.py` | Audit spawns/finishes; opt-in LLM summary (`SUBAGENT_SUMMARY=true`) |
| `PreCompact` / `PostCompact` | `pre_compact.py` / `post_compact.py` | Audit compaction; opt-in transcript backup (`BACKUP_TRANSCRIPT=true`) |
| `Stop` | `stop.py` | Audit every turn-end (+ Tier B validation when enabled) |

All are **fail-open** — any error exits 0 and the action proceeds untouched. The
optional behaviors are off by default and gated by the env vars shown above.

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

## The two feature flags

Everything is controlled by **two flags**. Each flow runs only when its flag is on.

| Flag | Flow it enables | Default | Set in `config.yaml` | Env override |
|------|-----------------|---------|----------------------|--------------|
| **Prompt rewrite** (Tier A) | Refine the user's prompt for typos/clarity at submit/expansion | **on** | `gates.always_rewrite` | `ENABLE_PROMPT_REWRITE=true\|false` |
| **TDD + unit-test validation** (Tier B) | Generate acceptance criteria from the prompt, then validate the final response at the Stop hook (block→retry) | **off** | `gates.enable_tdd` | `ENABLE_TDD=true\|false` |

Quick toggles:
```bash
export ENABLE_PROMPT_REWRITE=true   # flag 1: prompt rewrite
export ENABLE_TDD=true              # flag 2: TDD + validation
```

## Install the hooks into your `.claude` folder

The hooks run as plain Python scripts that Claude Code invokes. Two ways to wire them up:

### Option A — project-local (recommended for one repo)

1. **Copy this `hooks_v2/` directory into your project** (or keep it where it is).
2. **Install the dependencies:**
   ```bash
   pip install -r hooks_v2/requirements.txt
   ```
3. **Register the hooks** by copying the `hooks` block from
   [`settings.json`](settings.json) into your project's **`.claude/settings.json`**
   (create the file if it doesn't exist). It points at the scripts via
   `${CLAUDE_PROJECT_DIR}/hooks_v2/lifecycle_events/*.py`. A ready-to-copy file is
   provided — if your repo has no `.claude/settings.json` yet you can just do:
   ```bash
   mkdir -p .claude
   cp hooks_v2/settings.json .claude/settings.json
   ```
   If you already have a `.claude/settings.json`, merge the `hooks` keys in rather
   than overwriting.
4. **Verify** with `/hooks` inside Claude Code — you should see `UserPromptSubmit`,
   `UserPromptExpansion`, `PostToolUse` (`mcp__.*`), and `Stop` registered.

### Option B — global (all your projects)

Put the same `hooks` block in **`~/.claude/settings.json`** and use an absolute
path to the scripts (replace `${CLAUDE_PROJECT_DIR}/hooks_v2` with the absolute
install path).

### Option C — as a plugin

`hooks/hooks.json` + `.claude-plugin/plugin.json` make this a drop-in Claude Code
plugin; install it from a marketplace/plugin path and it self-registers via
`${CLAUDE_PLUGIN_ROOT}`.

## Authentication (no API key needed on a Max/Pro plan)

The default `agent_sdk` backend uses your **Claude subscription** via the Claude
Agent SDK — no per-token API key.

1. Generate a long-lived subscription token **once**:
   ```bash
   claude setup-token        # opens a browser login, prints a token
   export CLAUDE_CODE_OAUTH_TOKEN=...   # set it where the hooks run
   ```
   (A logged-in `claude` CLI also works without this token.)
2. **Make sure `ANTHROPIC_API_KEY` is _unset_** — if it's set, the SDK uses it and
   bills API rates instead of your subscription.

Prefer the pay-as-you-go API instead? Set `LLM_BACKEND=api` and `ANTHROPIC_API_KEY=...`.

> Without any working auth, the hooks **fail open** (no-op) — they never block or
> break a prompt; the rewrite/validation simply doesn't run.

## Configuration (`config.yaml` or env)

| Setting | Env | Default | Meaning |
|---------|-----|---------|---------|
| `anthropic.backend` | `LLM_BACKEND` | `agent_sdk` | `agent_sdk` (subscription) or `api` (API key) |
| `gates.always_rewrite` | `ENABLE_PROMPT_REWRITE` | `true` | **Flag 1** — Tier A prompt rewrite |
| `gates.enable_tdd` | `ENABLE_TDD` | `false` | **Flag 2** — Tier B generation + validation/retry |
| `gates.refine_confidence_threshold` | `REFINE_CONFIDENCE_THRESHOLD` | `0.30` | Apply the rewrite when intent-preservation confidence ≥ this |
| `tdd.max_cycles` | `TDD_MAX_CYCLES` | `3` | Retry cap |
| `tdd.pass_rate_threshold` | `TDD_PASS_THRESHOLD` | `0.95` | Pass bar |

Models: Tier A `claude-haiku-4-5`; Tier B gen/validate `claude-sonnet-4-6`; final cycle `claude-opus-4-8`.

## Run the automated tests

The suite is pure-Python and needs **no API key/subscription** (the LLM call is
mocked). From the repo root:

```bash
pip install -r hooks_v2/requirements-dev.txt   # pytest + runtime deps
python3 -m pytest hooks_v2/tests -q            # run everything (35 tests)
python3 -m pytest hooks_v2/tests -v            # verbose, per-test names
python3 -m pytest hooks_v2/tests/test_lifecycle.py -q   # one file
```

What the test files cover:

| File | Covers |
|------|--------|
| `tests/test_shared.py` | config flags/env overrides, JSON logger, JSON parsing, model costs |
| `tests/test_context.py` | the `ContextStore` save/load/clear + key helpers |
| `tests/test_category2.py` | Tier A refine (apply/skip/fail-open) and Tier B generate/validate |
| `tests/test_pipeline.py` | the shared refine+TDD pipeline and MCP audit edge cases |
| `tests/test_lifecycle.py` | end-to-end hook scripts: prompt rewrite, expansion rewrite, MCP audit, Stop block→retry→pass |

You can also smoke-test a hook by hand (no auth needed — it just no-ops the LLM):
```bash
echo '{"tool_name":"mcp__x__y","tool_input":{"q":"hi"},"tool_output":"ok","duration_ms":3}' \
  | python3 hooks_v2/lifecycle_events/post_tool_use.py   # writes an MCP audit record
```
