# Elmer — Claude Code Instructions

## Orientation

Read in this order:
1. **CLAUDE.md** (this file) — tech stack, rules, conventions
2. **DESIGN.md** — architecture, data model, module responsibilities
3. **DECISIONS.md** — ADRs with full rationale (23 recorded)
4. **ROADMAP.md** — phase history and deferred features
5. **README.md** — user-facing docs, install, full command reference
6. **GUIDE.md** — practical usage playbook, workflows, patterns

Elmer is an autonomous research tool that uses git branches as isolation boundaries and Claude Code sessions (`claude -p`) as workers. All four development phases complete.

## Tech Stack

- Python 3.11+ / uv / hatchling / src layout
- **Click** for CLI
- **SQLite** (stdlib `sqlite3`) for state — WAL mode
- **Git worktrees** for branch isolation — no directory copying
- **`claude -p`** (Claude Code print mode) for headless exploration sessions
- **tomllib** (stdlib 3.11+) for config
- No external database, no web framework, no async — deliberate simplicity

## Commands

Full options and examples in README.md. Core subcommands:

| Command | Purpose |
|---------|---------|
| `elmer init` | Scaffold `.elmer/` in current project (`--docs`, `--skills`) |
| `elmer explore "topic"` | Start exploration on a new branch (`-a`, `-m`, `--auto-approve`, `--budget`, etc.) |
| `elmer batch FILE` | Spawn from `---`-separated topic list file (`--chain`, `--dry-run`, `--item`) |
| `elmer generate` | AI-generate research topics and spawn explorations (`--count`, `--follow-up`, `--dry-run`) |
| `elmer status` | Show all explorations with state (`--all-projects` for dashboard) |
| `elmer tree` | Exploration dependency tree |
| `elmer review [ID]` | List pending proposals or show one (`--prioritize` for ranked review) |
| `elmer approve ID` | Merge branch, cleanup (`--all`, `--auto-followup`, `--validate-invariants`) |
| `elmer reject ID` | Discard branch, cleanup |
| `elmer cancel ID` | Stop running/pending exploration, cleanup |
| `elmer costs` | Cost summary (`--exploration ID` for detail) |
| `elmer validate` | Check document invariants |
| `elmer archetypes` | `list` or `stats` |
| `elmer mine-questions` | Extract open questions from docs (`--spawn`, `--cluster`) |
| `elmer insights` | List cross-project insights |
| `elmer daemon` | Continuous operation (`--auto-approve --generate` for full autonomy) |
| `elmer pr ID` | Push branch, create GitHub PR |
| `elmer clean` | Remove finished worktrees + state entries |

## Rules

### Constraints

- No external database servers. SQLite only.
- No async framework. Subprocess + PID tracking for background processes.
- Archetypes use `$TOPIC` substitution — no Jinja, no templating engine.
- Git worktrees, never directory copying. Worktrees share `.git`.
- `claude -p` for headless sessions, never Agent Teams (session-scoped, don't persist).

### Design Principles

- **Demonstrate value before adding complexity.** Each phase justified the next.
- **Project-aware but not project-prescriptive.** Reads CLAUDE.md/CONTEXT.md if present, works without them.
- **Git is the coordination layer.** Branches for isolation, merge for integration, worktrees for parallelism.
- **Conservative auto-approve defaults.** `--auto-approve` is opt-in. AI review gate rejects when uncertain.

## Identifier Conventions

- **ADR-NNN** — Architecture Decision Records. Numbered sequentially, never reused. Header format: `## ADR-NNN: Title` in DECISIONS.md.

## Document Maintenance

| File | Role | Update when... |
|------|------|---------------|
| **CLAUDE.md** | Instructions | Rules change, tech stack changes, ADR count changes |
| **DESIGN.md** | Architecture | Architecture changes, modules added/removed |
| **DECISIONS.md** | ADR registry | Any non-trivial design choice (revise in place, git is the audit trail) |
| **ROADMAP.md** | Phase history | Deferred features added or resolved |
| **README.md** | User-facing | Commands change, new archetypes, install changes |
| **GUIDE.md** | Playbook | New workflows, new patterns, usage advice evolves |

### Canonical Homes

Each piece of information lives in one place. Other files reference, not duplicate.

| Information | Canonical home |
|-------------|---------------|
| Tech stack | CLAUDE.md |
| Full command reference | README.md |
| Module responsibilities | DESIGN.md |
| ADR list + rationale | DECISIONS.md |
| Phase history | ROADMAP.md |
| Workflows and patterns | GUIDE.md |
| Architecture diagrams & schemas | DESIGN.md |

### Per-Session Checklist

1. If you added ADRs → update count in CLAUDE.md Orientation ("23 recorded") and DECISIONS.md header
2. If architecture changed → update DESIGN.md
3. If commands changed → update README.md
4. Update last-updated footer on every modified document

### Documentation Rules

- **ADRs are mutable living documents.** Update directly — add, revise, or replace content in place. When substantially revising, add `*Revised: [date], [reason]*` at the section's end. Git history is the audit trail.
- **Section-level change tracking.** When substantially revising a DESIGN.md section or an ADR, add `*Revised: [date], [reason or ADR]*` at the section's end.
- **No duplication across documents.** If information exists in its canonical home, other documents reference it. The ADR list lives only in DECISIONS.md. The command reference lives only in README.md.

*Last updated: 2026-02-23, added cancel command, cycle detection, chain rejection warnings*
