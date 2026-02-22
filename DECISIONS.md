# Elmer — Decisions

Architecture Decision Records. Append-only — never edit past entries. If a decision is superseded, record a new ADR with rationale.

6 ADRs recorded.

## Domain Index

| ADR | Domain | Summary |
|-----|--------|---------|
| ADR-001 | Git | Worktrees over directory copying |
| ADR-002 | Process | Background `claude -p` over Agent Teams |
| ADR-003 | Storage | SQLite over JSON state files |
| ADR-004 | CLI | Click over argparse |
| ADR-005 | Prompts | Static templates before generated prompts |
| ADR-006 | Architecture | No daemon in Phase 1 |

---

## ADR-001: Git Worktrees Over Directory Copying

**Decision:** Use git worktrees for branch isolation, not directory copying.

Worktrees share `.git`, are instant to create, and space-efficient. Directory copying wastes disk, duplicates git history, and creates confusion about which copy is canonical. Worktrees provide real branch isolation with minimal overhead.

**Alternatives considered:** Directory copying (cp -r), temporary git clones.

## ADR-002: Background Processes Over Agent Teams

**Decision:** Use background `claude -p` processes, not Claude Code Agent Teams.

Agent Teams are session-scoped and don't persist across Claude Code sessions. Elmer explorations should outlive any single session — start explorations, close your terminal, review tomorrow. Background `claude -p` processes provide this persistence.

**Alternatives considered:** Agent Teams (session-scoped, don't persist), Claude Code plugin hooks (wrong lifecycle).

## ADR-003: SQLite Over JSON State Files

**Decision:** Use SQLite with WAL mode for state, not JSON files.

Concurrent explorations writing to a single JSON file risk corruption. SQLite handles concurrent access correctly via WAL mode. It also supports queries (find all explorations by status) without loading everything into memory.

**Alternatives considered:** Single JSON file, one JSON file per exploration.

## ADR-004: Click Over Argparse

**Decision:** Use Click for CLI, not argparse.

Click produces cleaner subcommand handling, better help text, and composable decorators. The single dependency is worth the ergonomic improvement for a CLI tool.

**Alternatives considered:** argparse (stdlib, no dependency but verbose), Typer (heavier, type-annotation magic).

## ADR-005: Static Templates Before Generated Prompts

**Decision:** Use static archetype templates with `$TOPIC` substitution in Phase 1. Defer two-stage prompt generation to Phase 2.

Static templates are debuggable, predictable, and sufficient for initial use. Two-stage generation (AI generates the prompt, then AI executes it) is the architectural goal but adds complexity that isn't justified until the core loop proves useful.

**Alternatives considered:** Jinja templating (overkill), AI-generated prompts from day one (premature complexity).

## ADR-006: No Daemon in Phase 1

**Decision:** No daemon or continuous loop in Phase 1. Manual CLI only.

The daemon (continuous loop: generate topics → spawn explorations → harvest → gate) adds complexity and requires cost controls. Phase 1 proves the core loop manually. If the manual loop is useful, the daemon is justified in Phase 2.

**Alternatives considered:** Ship daemon immediately (risk: overbuilt before proving value).

*Last updated: Phase 1*
