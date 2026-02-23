# Elmer — Roadmap

All four phases complete. Git history has the full delivery record.

## Phase 1: Core Loop — COMPLETE

Manual explore → review → approve/reject. CLI primitives, git worktree isolation, SQLite state, three archetypes. Proved the loop is useful on a real project.

## Phase 2: Intelligence — COMPLETE

AI topic generation, DAG dependencies, auto-approve gate, two-stage prompt generation, cost controls, archetype evolution (8 exploration archetypes + AI selection).

## Phase 3: Autonomy — COMPLETE

Daemon loop, conditional chain actions, follow-up generation, cross-project insight log, question mining. Overnight autonomous operation with budget caps.

## Phase 4: Meta — COMPLETE

Project scaffolding, template evolution stats, attention routing, document invariant enforcement, multi-project dashboard, PR-based review, batch topic lists, skill scaffolding.

---

## Deferred / Uncertain

Features discussed but not committed:

- **Shared template library** — single source for analysis methodology shared between Elmer archetypes and Claude Code skills. Deferred because drift between the two systems is tolerable and the indirection cost exceeds the sync benefit.
- **Web UI for review** — local web server showing proposals with rich formatting. CLI review is sufficient for now.
- **Elmer-on-Elmer recursion** — Elmer running explorations on its own codebase.
- **Agent Teams integration** — within a single exploration, the Claude session could use Agent Teams for parallel sub-tasks. Emergent from claude's own capabilities, no Elmer changes needed.
## Phase 5: Integration — COMPLETE

MCP server exposing Elmer state and operations as structured tools (ADR-024). 10 tools over stdio JSON-RPC: 6 read-only (status, review, costs, tree, archetypes, insights) + 4 mutation (explore, approve, reject, cancel).

*Last updated: 2026-02-23, MCP server Phase 2 complete*
