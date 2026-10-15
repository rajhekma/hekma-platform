# Claude Project Instructions

Use the repository's shared AI context system (`docs/ai/`).

## Before Significant Tasks
1. Read `AGENTS.md`.
2. Read `docs/ai/CONTEXT.md` for a concise overview (~500–1000 words).
3. Read only the relevant service context: `docs/ai/services/identity.md`.
4. Inspect only the source files relevant to the task.

## Context Reference Navigation
- **Architecture & System Design**: `docs/ai/ARCHITECTURE.md`
- **Technical Decisions & ADRs**: `docs/ai/DECISIONS.md`
- **Current Development State & Blockers**: `docs/ai/CURRENT.md`
- **Coding, Testing & Error Conventions**: `docs/ai/CONVENTIONS.md`

## Invariants & Rules
- Do not scan the entire repository unnecessarily; use targeted lookups.
- The codebase and Git history are the ultimate source of truth.
- When asked to prepare a plan, produce ONLY planning documentation. Never modify application code directly.
- NEVER run `git commit` or `git push` unless explicitly instructed.
- After significant changes, update the relevant shared AI documentation according to `AGENTS.md`.
- Do not create a separate Claude-only project knowledge base.
