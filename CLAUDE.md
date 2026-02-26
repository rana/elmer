# Elmer — Claude Code Instructions

## Orientation

Read in this order:
1. **CLAUDE.md** (this file) — tech stack, rules, conventions
2. **CONTEXT.md** — project methodology, collaboration model, current state
3. **DESIGN.md** — architecture, data model, module responsibilities
4. **DECISIONS.md** — ADRs with full rationale (59 recorded)
5. **ROADMAP.md** — phase history, **Future Directions** (remaining improvements), deferred features
6. **README.md** — user-facing docs, install, full command reference
7. **GUIDE.md** — practical usage playbook, workflows, patterns

Elmer is an autonomous research tool that uses git branches as isolation boundaries and Claude Code sessions (`claude -p`) as workers. All seven development phases complete.

### Active Backlog

10 of 22 new future directions resolved: G1–G3 (worker intelligence — digest/sibling/decline injection), H1–H3 (proposal quality — confidence annotations, structured schema, review notes), E3 (ensemble synthesis failure recovery), A4 (exploration-to-plan pipeline), I1 (archetype effectiveness diagnosis), B3 (per-step model routing). 12 remain: G4, I2, J1–J4, B2, C4, D3, D5, E1–E2. See ROADMAP.md Future Directions for full details.

## Tech Stack

- Python 3.11+ / uv / hatchling / src layout
- **Click** for CLI
- **SQLite** (stdlib `sqlite3`) for state — WAL mode
- **Git worktrees** for branch isolation — no directory copying
- **`claude -p`** (Claude Code print mode) for headless exploration sessions
- **tomllib** (stdlib 3.11+) for config
- **`mcp`** (FastMCP) for MCP server — structured tool access over stdio
- No external database, no web framework, no async — deliberate simplicity

## Commands

Full options and examples in README.md. Core subcommands:

| Command | Purpose |
|---------|---------|
| `elmer init` | Scaffold `.elmer/` in current project (`--docs`, `--skills`, `--agents`) |
| `elmer explore "topic"` | Start exploration on a new branch (`-a`, `-m`, `--auto-approve`, `--replicas`, `--archetypes`, `--models`, `--verify-cmd`) |
| `elmer batch FILE` | Spawn from `---`-separated topic list file (`--chain`, `--dry-run`, `--item`, `--max-concurrent`, `--stagger`, `--replicas`) |
| `elmer generate` | AI-generate research topics and spawn explorations (`--count`, `--follow-up`, `--dry-run`) |
| `elmer status` | Show all explorations with state (`-v` for topics, `--all-projects` for dashboard) |
| `elmer tree` | Exploration dependency tree |
| `elmer review [ID]` | List pending proposals or show one (`--prioritize` for ranked review) |
| `elmer approve ID` | Merge branch, auto-clean (`--all`, `--auto-followup`, `--validate-invariants`, `--no-clean`) |
| `elmer amend ID "feedback"` | Revise proposal in existing worktree (`-m`, `--max-turns`) |
| `elmer decline ID [REASON]` | Discard branch, cleanup (optional reason feeds digest) |
| `elmer digest` | Synthesize convergence digest from recent explorations (`--since`, `--topic`) |
| `elmer cancel ID` | Stop running/pending/amending exploration, cleanup |
| `elmer retry [ID]` | Retry failed exploration(s) (`--failed`, `--max-concurrent`) |
| `elmer costs` | Cost summary (`--exploration ID` for detail) |
| `elmer validate` | Check document invariants (`--check` for read-only; exits 1 on failure) |
| `elmer archetypes` | `list`, `stats`, or `diagnose NAME` |
| `elmer mine-questions` | Extract open questions from docs (`--spawn`, `--cluster`) |
| `elmer insights` | List cross-project insights |
| `elmer daemon` | Continuous operation (`--auto-approve --generate` for full autonomy) |
| `elmer logs ID` | Session log diagnostics (`--raw` for JSON) |
| `elmer pr ID` | Push branch, create GitHub PR |
| `elmer clean` | Remove failed/orphaned worktrees + state entries (garbage collection) |
| `elmer block ID DESC` | Register external blocker (stakeholder decision, prerequisite) |
| `elmer unblock ID` | Resolve external blocker, unblocking dependent explorations |
| `elmer blockers` | List all external blockers with status |
| `elmer implement "milestone"` | Decompose milestone into steps, execute autonomously (`--dry-run`, `--save`, `--answers-file`, `--load-plan`, `--steps`, `--status`, `--resume`, `--from-exploration`) |
| `elmer replan ID [CONTEXT]` | Revise a paused plan when step failure is structural (`--dry-run`, `--save`, `-m`) |
| `elmer mcp` | Start MCP server — 25 tools for Claude Code integration |

## Rules

### Constraints

- No external database servers. SQLite only.
- No async framework. Subprocess + PID tracking for background processes.
- Archetypes as Claude Code custom subagents (ADR-026, ADR-053) — agent-only resolution, no template fallback.
- Git worktrees, never directory copying. Worktrees share `.git`.
- `claude -p` with `--agents`/`--agent` flags for headless sessions, never Agent Teams (session-scoped, don't persist).

### Design Principles

- **Demonstrate value before adding complexity.** Each phase justified the next.
- **Project-aware but not project-prescriptive.** Reads CLAUDE.md/CONTEXT.md if present, works without them.
- **Git is the coordination layer.** Branches for isolation, merge for integration, worktrees for parallelism.
- **Conservative auto-approve defaults.** `--auto-approve` is opt-in. AI review gate declines when uncertain.

## Identifier Conventions

- **ADR-NNN** — Architecture Decision Records. Numbered sequentially, never reused. Header format: `## ADR-NNN: Title` in DECISIONS.md.

## Document Maintenance

Seven files. Keep them accurate — drift compounds across sessions.

| When this happens... | ...update these documents |
|----------------------|--------------------------|
| New ADR added | DECISIONS.md (ADR + domain index + count), CLAUDE.md (ADR count in Orientation) |
| Module added or removed | DESIGN.md (module table, data flow) |
| Command added or changed | README.md (command table, options), CLAUDE.md (command table) |
| New workflow or pattern discovered | GUIDE.md |
| Deferred feature added or resolved | CONTEXT.md (open questions), ROADMAP.md (deferred section) |
| Project purpose or methodology evolves | CONTEXT.md |
| Rules or constraints change | CLAUDE.md |
| Tech stack changes | CLAUDE.md (tech stack section) |
| MCP tool added or changed | `mcp_server.py`, DESIGN.md (MCP server tables), ROADMAP.md (Phase 5), CLAUDE.md (tool count) |

At phase boundaries, reconcile all documents for consistency.

### Canonical Homes

Each piece of information lives in one place. Other files reference, not duplicate.

| Information | Canonical home |
|-------------|---------------|
| Tech stack | CLAUDE.md |
| Project methodology & context | CONTEXT.md |
| Full command reference | README.md |
| Module responsibilities | DESIGN.md |
| ADR list + rationale | DECISIONS.md |
| Phase history | ROADMAP.md |
| Deferred features & open questions | CONTEXT.md |
| Workflows and patterns | GUIDE.md |
| Architecture diagrams & schemas | DESIGN.md |

### Per-Session Checklist

1. If you added ADRs → update count in CLAUDE.md Orientation ("11 recorded") and DECISIONS.md header
2. If architecture changed → update DESIGN.md
3. If commands changed → update README.md
4. Update last-updated footer on every modified document

### Documentation Rules

- **ADRs are mutable living documents.** Update directly — add, revise, or replace content in place. When substantially revising, add `*Revised: [date], [reason]*` at the section's end. Git history is the audit trail.
- **Section-level change tracking.** When substantially revising a DESIGN.md section or an ADR, add `*Revised: [date], [reason or ADR]*` at the section's end.
- **No duplication across documents.** If information exists in its canonical home, other documents reference it. The ADR list lives only in DECISIONS.md. The command reference lives only in README.md.

*Last updated: 2026-02-26, autonomous operation — failure taxonomy, trust escalation, config validation, retry policy, key-files flow, 218 tests (ADR-076), 59 ADRs*
