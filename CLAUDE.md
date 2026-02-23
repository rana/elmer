# Elmer — Claude Code Instructions

## Orientation

Read in this order:
1. **CLAUDE.md** (this file) — tech stack, commands, rules
2. **DESIGN.md** — architecture, data model, ADRs, planned features
3. **ROADMAP.md** — 4-phase plan from manual CLI to autonomous daemon
4. **README.md** — user-facing docs, install, quick start
5. **GUIDE.md** — practical usage playbook, workflows, patterns

Elmer is an autonomous research tool that uses git branches as isolation boundaries and Claude Code sessions (`claude -p`) as workers. It works with any git project. Named after Elmer Fudd — persistent hunter, homage to the Ralph Wiggum naming tradition.

**Current state:** Phase 4 complete. All features implemented: project scaffolding, template evolution, attention routing, document invariant enforcement, multi-project dashboard, PR-based review, batch topic lists, Claude Code skill scaffolding. 23 ADRs recorded.

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
elmer init --docs                       # Also scaffold CLAUDE.md, DESIGN.md, etc.
elmer init --skills                     # Scaffold Claude Code skills from project docs
elmer init --docs --skills              # Scaffold both docs and skills

# Explore
elmer explore "topic"                   # Default archetype + model from config
elmer explore "topic" -a prototype      # Use prototype archetype
elmer explore "topic" -m opus           # Use opus model
elmer explore -f topics.txt             # Batch: one topic per line
elmer explore "topic" --max-turns 100   # Override turn limit
elmer explore "topic" --depends-on ID   # Block until ID is approved
elmer explore "topic" --auto-approve    # AI review gate when done
elmer explore "topic" --auto-archetype  # AI picks best archetype for topic
elmer explore "topic" --generate-prompt # AI-generated exploration prompt
elmer explore "topic" --budget 2.00    # Cap cost at $2
elmer explore "topic" --on-approve "elmer generate --follow-up \$ID"
elmer explore "topic" --on-reject "elmer explore 'alt to \$TOPIC'"

# Batch
elmer batch .elmer/explore-act.md              # Spawn from topic list file
elmer batch .elmer/explore-act.md --dry-run    # Preview parsed topics
elmer batch .elmer/explore-act.md --chain      # Sequential (each depends on previous)
elmer batch .elmer/explore-act.md --item 2     # Run only item 2
elmer batch .elmer/prototype.md -m opus        # Override model
elmer batch .elmer/explore-act.md --budget 10  # Total budget, divided across topics

# Generate
elmer generate                          # AI generates 5 topics, auto-spawns
elmer generate --count 3 --dry-run      # Preview 3 topics without spawning
elmer generate --follow-up ID           # Follow-ups to a completed exploration
elmer generate -m haiku --count 10      # Cheap broad generation
elmer generate --auto-approve           # All spawned explorations auto-reviewed
elmer generate --auto-archetype         # AI picks archetype per topic
elmer generate --budget 5.00           # $1 per exploration (5 topics)

# Monitor
elmer status                            # All explorations with status
elmer status --all-projects             # Overview across all registered projects
elmer tree                              # Exploration dependency tree

# Review
elmer review                            # List proposals pending review
elmer review ID                         # Show full proposal
elmer review --prioritize               # Rank proposals by review priority

# Gate
elmer approve ID                        # Merge branch, cleanup worktree
elmer approve --all                     # Approve all pending
elmer approve ID --auto-followup        # Generate follow-ups after merge
elmer approve ID --followup-count 5     # Control follow-up count
elmer approve ID --validate-invariants  # Check doc consistency after merge
elmer reject ID                         # Delete branch, cleanup worktree

# Costs
elmer costs                             # Cost summary for all explorations
elmer costs --exploration ID            # Cost detail for one exploration

# Validation
elmer validate                          # Check document invariants
elmer validate -m haiku                 # Quick check with haiku

# Archetypes
elmer archetypes list                   # Available archetypes (local + bundled)
elmer archetypes stats                  # Archetype effectiveness statistics

# Question Mining
elmer mine-questions                    # Extract open questions from project docs
elmer mine-questions --cluster "API"    # Filter to a cluster
elmer mine-questions --spawn            # Explore all mined questions
elmer mine-questions --spawn --cluster "API"  # Explore one cluster

# Insights
elmer insights                          # List cross-project insights

# Daemon
elmer daemon                            # Start daemon (default interval)
elmer daemon --interval 300             # 5-minute cycle interval
elmer daemon --auto-approve --generate  # Full autonomy mode
elmer daemon --audit --auto-approve     # Audit mode (rotate scheduled audits)
elmer daemon --auto-archetype --generate  # AI picks archetypes for topics
elmer daemon --budget 5.00              # Cost cap per cycle
elmer daemon --max-concurrent 3         # Limit parallel explorations
elmer daemon --auto-followup            # Generate follow-ups after approvals
elmer daemon status                     # Check if daemon is running
elmer daemon stop                       # Graceful shutdown

# Pull Requests
elmer pr ID                             # Push branch, create GitHub PR

# Cleanup
elmer clean                             # Remove finished worktrees + state entries
```

## Project Structure

```
src/elmer/
├── cli.py              # Click CLI entry point
├── batch.py            # Topic list file parsing for batch command
├── explore.py          # Orchestration: worktree → prompt → worker → state
├── review.py           # Status display, proposal reading, attention routing
├── gate.py             # Approve (merge) / reject (discard)
├── worktree.py         # Git worktree + branch operations
├── worker.py           # claude -p invocation, PID tracking
├── state.py            # SQLite CRUD
├── config.py           # Config loading, project init, archetype resolution
├── generate.py         # AI topic generation orchestration
├── autoapprove.py      # AI review gate for auto-approval
├── promptgen.py        # Two-stage AI prompt generation
├── archselect.py       # AI archetype selection
├── costs.py            # Cost reporting and summaries
├── daemon.py           # Daemon loop, PID management, cycle execution
├── insights.py         # Cross-project insight extraction and injection
├── questions.py        # Question mining from project documentation
├── scaffold.py         # Project scaffolding (five-document pattern)
├── skill_scaffold.py   # Claude Code skill scaffolding
├── archstats.py        # Archetype effectiveness statistics
├── invariants.py       # Document invariant enforcement
├── dashboard.py        # Multi-project status aggregation
├── pr.py               # PR creation via gh CLI
└── archetypes/         # Bundled default templates
    ├── explore.md      # Read-only analysis
    ├── explore-act.md  # Biased toward action proposals
    ├── prototype.md    # Write working code on branch
    ├── adr-proposal.md     # Propose architecture decisions
    ├── question-cluster.md # Explore clusters of related questions
    ├── benchmark.md        # Measure and evaluate
    ├── dead-end-analysis.md # Analyze potential dead ends
    ├── devil-advocate.md   # Challenge assumptions
    ├── consistency-audit.md    # Subsystem consistency & reasoning sufficiency
    ├── coherence-audit.md      # Cross-reference integrity across docs
    ├── architecture-audit.md   # Pattern compliance, drift, emerging patterns
    ├── operational-audit.md    # Ops readiness, cost, resilience
    ├── documentation-audit.md  # Doc practice quality, staleness
    ├── opportunity-scan.md     # Emergent opportunities, simplifications
    ├── workflow-audit.md       # End-to-end workflow tracing
    ├── mission-audit.md        # Alignment with stated principles
    ├── generate-topics.md  # Meta-prompt for topic generation
    ├── prompt-gen.md       # Meta-prompt for two-stage prompt generation
    ├── review-gate.md      # Prompt for auto-approve review
    ├── select-archetype.md # Meta-prompt for AI archetype selection
    ├── extract-insights.md # Meta-prompt for insight extraction
    ├── mine-questions.md   # Meta-prompt for question mining
    └── validate-invariants.md  # Meta-prompt for invariant enforcement
```

## Per-Project Layout (created by `elmer init`)

```
.elmer/
├── config.toml        # Defaults (committed)
├── archetypes/        # Project-specific templates (committed)
├── <archetype>.md     # Topic list files for batch command (committed, optional)
├── .gitignore         # Excludes worktrees/, logs/, state.db, daemon.pid
├── worktrees/         # Git worktrees (gitignored)
├── logs/              # Claude session logs + daemon.log (gitignored)
├── state.db           # SQLite state (gitignored)
└── daemon.pid         # Daemon PID file (gitignored)
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

## Identifier Conventions

- **ADR-NNN** — Architecture Decision Records. Numbered sequentially, never reused. Header format: `## ADR-NNN: Title` in DECISIONS.md. Referenced in prose as `ADR-001`.

## Document Maintenance

| File | Type | Update when... |
|------|------|---------------|
| **CLAUDE.md** | Living | Commands change, rules change, phase completes, ADR count changes |
| **DESIGN.md** | Stable + Planned | Architecture changes, planned features marked as implemented |
| **DECISIONS.md** | Living | Any non-trivial design choice (revise in place, git is the audit trail) |
| **ROADMAP.md** | Living | Phase status changes, deliverables complete or deferred |
| **README.md** | Stable | User-facing changes (new commands, new archetypes) |
| **GUIDE.md** | Living | New workflows, new patterns, usage advice evolves with features |

### Per-Session Checklist

1. If you added ADRs → update count in CLAUDE.md Orientation and DECISIONS.md
2. If phase status changed → update ROADMAP.md phase header
3. If architecture implemented → mark DESIGN.md section with `**Status: Implemented** — see src/elmer/<module>`
4. Update last-updated footer on every modified document

### Document Invariants

These must hold after each session. Violations indicate drift:
- ADR count in CLAUDE.md Orientation == actual `## ADR-` entries in DECISIONS.md
- Phase status in ROADMAP.md matches "Current state" in CLAUDE.md Orientation
- No planned feature marked COMPLETE in ROADMAP.md without corresponding code in `src/elmer/`
- Tech stack canonical home is CLAUDE.md — other files reference, not duplicate

### Documentation–Code Transition

1. **Before implementation:** DESIGN.md is the source of truth. Code follows it.
2. **When a section is implemented:** Add `**Status: Implemented** — see src/elmer/<module>` at the top.
3. **When implementation diverges from design:** Update DESIGN.md to reflect the actual decision.
4. **ADRs are mutable living documents.** Update them directly — add, revise, or replace content in place. Do not create superseding ADRs or use withdrawal ceremony. When substantially revising an ADR, add `*Revised: [date], [reason]*` at the section's end. Git history serves as the full audit trail.
5. **Section-level change tracking.** When substantially revising a DESIGN.md section or an ADR, add `*Revised: [date], [reason or ADR]*` at the section's end.

### Scaling Strategy

- **DECISIONS.md:** At 20+ ADRs, consider splitting into DECISIONS_ARCHIVE.md (Phase 1-2) and current. Maintain a domain index linking both.
- **DESIGN.md:** At 20+ sections, add a navigation table at top with phase annotations.

## Key Design Decisions (Summary)

Full rationale in DECISIONS.md. 23 ADRs recorded.

- **ADR-001:** Git worktrees over directory copying
- **ADR-002:** Background `claude -p` processes over Agent Teams
- **ADR-003:** SQLite over JSON state files
- **ADR-004:** Click over argparse
- **ADR-005:** Static templates before generated prompts
- **ADR-006:** Daemon deferred to Phase 3
- **ADR-007:** Synchronous `claude -p` for meta-operations
- **ADR-008:** JSON output format for cost extraction
- **ADR-009:** AI archetype selection as a meta-operation
- **ADR-010:** Daemon as composition layer
- **ADR-011:** PID file for daemon coordination
- **ADR-012:** Chain actions as shell commands
- **ADR-013:** Global insights database at ~/.elmer/
- **ADR-014:** Question mining as meta-operation
- **ADR-015:** Five-document scaffolding as templates
- **ADR-016:** Archetype stats from existing exploration data
- **ADR-017:** Heuristic attention routing
- **ADR-018:** Invariant enforcement as meta-operation
- **ADR-019:** Global project registry for multi-project dashboard
- **ADR-020:** PR creation via gh CLI
- **ADR-021:** Topic list files with batch command
- **ADR-022:** Claude Code skill scaffolding as Elmer feature
- **ADR-023:** Mutable ADRs with git audit trail

## What's Next

See ROADMAP.md for the full 4-phase plan. All four phases complete. See Deferred / Uncertain in ROADMAP.md for potential future work.

*Last updated: coherence audit — ADR header format convention, invariant grep pattern*
