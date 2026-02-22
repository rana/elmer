# Elmer — Claude Code Instructions

## Orientation

Read in this order:
1. **CLAUDE.md** (this file) — tech stack, commands, rules
2. **DESIGN.md** — architecture, data model, ADRs, planned features
3. **ROADMAP.md** — 4-phase plan from manual CLI to autonomous daemon
4. **README.md** — user-facing docs, install, quick start

Elmer is an autonomous research tool that uses git branches as isolation boundaries and Claude Code sessions (`claude -p`) as workers. It works with any git project. Named after Elmer Fudd — persistent hunter, homage to the Ralph Wiggum naming tradition.

**Current state:** Phase 1 complete. Core loop works end-to-end: explore → status → review → approve/reject. Tested live against Mercury (produced substantive PROPOSAL.md with haiku in ~2 minutes). 6 ADRs recorded.

## Tech Stack

- Python 3.11+ / uv / hatchling / src layout
- **Click** for CLI
- **SQLite** (stdlib `sqlite3`) for state — WAL mode, single table
- **Git worktrees** for branch isolation — no directory copying
- **`claude -p`** (Claude Code print mode) for headless exploration sessions
- **tomllib** (stdlib 3.11+) for config
- No external database, no web framework, no async — deliberate simplicity

## Commands

```bash
# Setup
elmer init                              # Create .elmer/ in current project

# Explore
elmer explore "topic"                   # Default archetype + model from config
elmer explore "topic" -a prototype      # Use prototype archetype
elmer explore "topic" -m opus           # Use opus model
elmer explore -f topics.txt             # Batch: one topic per line
elmer explore "topic" --max-turns 100   # Override turn limit

# Monitor
elmer status                            # All explorations with status

# Review
elmer review                            # List proposals pending review
elmer review ID                         # Show full proposal

# Gate
elmer approve ID                        # Merge branch, cleanup worktree
elmer approve --all                     # Approve all pending
elmer reject ID                         # Delete branch, cleanup worktree

# Cleanup
elmer clean                             # Remove finished worktrees + state entries
```

## Project Structure

```
src/elmer/
├── cli.py              # Click CLI entry point
├── explore.py          # Orchestration: worktree → prompt → worker → state
├── review.py           # Status display, proposal reading
├── gate.py             # Approve (merge) / reject (discard)
├── worktree.py         # Git worktree + branch operations
├── worker.py           # claude -p invocation, PID tracking
├── state.py            # SQLite CRUD
├── config.py           # Config loading, project init, archetype resolution
└── archetypes/         # Bundled default templates
    ├── explore.md      # Read-only analysis
    ├── explore-act.md  # Biased toward action proposals
    └── prototype.md    # Write working code on branch
```

## Per-Project Layout (created by `elmer init`)

```
.elmer/
├── config.toml        # Defaults (committed)
├── archetypes/        # Project-specific templates (committed)
├── .gitignore         # Excludes worktrees/, logs/, state.db
├── worktrees/         # Git worktrees (gitignored)
├── logs/              # Claude session logs (gitignored)
└── state.db           # SQLite state (gitignored)
```

## Rules

### Constraints

- No external database servers. SQLite only.
- No async framework. Subprocess + PID tracking for background processes.
- Archetypes use `$TOPIC` substitution — no Jinja, no templating engine.
- Git worktrees, never directory copying. Worktrees share `.git`.
- `claude -p` for headless sessions, never Agent Teams (session-scoped, don't persist).

### Design Principles

- **Demonstrate value before adding complexity.** Phase 1 proves the manual loop. Daemon only if manual is useful.
- **Project-aware but not project-prescriptive.** Reads CLAUDE.md/CONTEXT.md if present, works without them.
- **Git is the coordination layer.** Branches for isolation, merge for integration, worktrees for parallelism.
- **Conservative auto-approve defaults.** `--auto-approve` is opt-in. AI review gate should reject when uncertain.

## Document Maintenance

| File | Type | Update when... |
|------|------|---------------|
| **CLAUDE.md** | Living | Commands change, rules change, phase completes |
| **DESIGN.md** | Stable + Planned | Architecture changes, new ADRs, planned features clarified |
| **ROADMAP.md** | Living | Phase status changes, features complete or deferred |
| **README.md** | Stable | User-facing changes (new commands, new archetypes) |

## Key Design Decisions (Summary)

Full rationale in DESIGN.md.

- **ADR-001:** Git worktrees over directory copying
- **ADR-002:** Background `claude -p` processes over Agent Teams
- **ADR-003:** SQLite over JSON state files
- **ADR-004:** Click over argparse
- **ADR-005:** Static templates before generated prompts
- **ADR-006:** No daemon in Phase 1

## What's Next

See ROADMAP.md for the full 4-phase plan. Key Phase 2 features:
- `elmer generate` — AI topic generation from project docs
- `elmer daemon` — continuous exploration loop
- `--auto-approve` — AI review gate
- `--depends-on` — DAG dependencies between explorations
- Two-stage prompt generation (AI generates the prompt, then AI executes it)

*Last updated: Phase 1 complete*
