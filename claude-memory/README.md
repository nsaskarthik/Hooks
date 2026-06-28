# claude-memory

Private, **auto-committed** memory / knowledge store for Claude Code — the *data* half of
the two-repo design (the *engine* lives in `hooks/`).

It currently lives as a folder inside the `Hooks` repo because this cloud session can't
reach the standalone `nsaskarthik/claude-memory` repo. The layout maps 1:1 to that repo,
so it can be split out later with no structural change (move the folder, `git init`, push).

The hooks write here — you don't edit these by hand:
- **Stop hook** appends an entry only when a turn produced something notable, then commits
  *only* the memory files (event-driven: no new memory → no commit).
- **SessionStart hook** injects the bounded `HOT.md` so any device/session resumes with
  current context.

## Tiers
- `HOT.md`         — small, curated digest injected every session (constant size).
- `log/`           — WARM: full append-only history (searched, not injected).
- `archive/`       — COLD: compacted / rolled-up old entries.
- `user_memory.md` — GLOBAL: preferences + reusable lessons (cross-project).
