# Elmer — Design

## Core Concept

Elmer is an autonomous research tool that uses git branches as isolation boundaries and Claude Code sessions as workers. Each exploration runs on its own branch in a git worktree. A human reviews the output and decides whether to merge.

```
                ┌──────────┐
                │  EXPLORE  │
   topic ──────▶│ worktree  │──────▶ PROPOSAL.md
                │ claude -p │
                └──────────┘
                      │
              ┌───────┴───────┐
              │               │
        ┌─────▼─────┐  ┌─────▼─────┐
        │  APPROVE   │  │  REJECT   │
        │ git merge  │  │ git rm    │
        └───────────┘  └───────────┘
```

## Philosophy

### What Elmer Is

A **persistent autonomous research layer** between you and your projects. Claude Code sessions are ephemeral — you open them, work, close them. Elmer persists. It remembers what was explored, what was approved, what failed, what chains are in progress. The closest analogy is a research assistant who works while you sleep, leaves proposals on your desk, and starts the next investigation based on what you approved yesterday.

Git branches are the desk. PROPOSAL.md is the memo. `elmer approve` is your signature.

### Why Elmer Exists

Two observations led here:

1. **Claude Code sessions are powerful but ephemeral.** Each session starts fresh. Research insights, design proposals, and exploratory work die with the session unless manually preserved. Elmer makes exploration persistent — branches survive sessions, proposals accumulate, research trees grow across days.

2. **Multiple projects share a cognition pattern.** Mercury (autonomous trading) and SRF (spiritual teachings portal) both use the same five-document structure: CONTEXT.md, DESIGN.md, DECISIONS.md, ROADMAP.md, CLAUDE.md. Both have `/explore` commands with identical templates. Elmer operationalizes this pattern — it reads those documents for context, explores topics autonomously, and produces proposals that fit the project's existing structure.

### Core Principles

**Git is the coordination layer.** Not a database, not a message queue, not a shared filesystem. Branches provide isolation. Merge provides integration. Worktrees provide parallelism. These are simple primitives with decades of reliability behind them.

**Demonstrate value before adding complexity.** Phase 1 proves the manual loop works. The daemon exists only if manual exploration is useful. Auto-approve exists only if human-gated exploration is useful. Each phase justifies the next. This mirrors Mercury's own principle: "demonstrate intelligence before deploying capital."

**Project-aware but not project-prescriptive.** Elmer reads CLAUDE.md, CONTEXT.md, DESIGN.md if they exist. It works without them. The five-document pattern is a convention that makes Elmer more effective, not a requirement Elmer imposes.

**Templates are scaffolding, not the destination.** Phase 1 uses static archetypes with `$TOPIC` substitution. The real architecture is two-stage prompt generation (Phase 2) where AI generates the optimal exploration prompt given the project's state and the topic's nature. Static templates are debuggable and predictable. Generated prompts are adaptive and project-aware. The transition is deliberate.

**Conservative autonomy.** Auto-approve is opt-in, default off. The AI review gate rejects when uncertain. Better to queue 5 proposals for human review than to merge 1 bad proposal autonomously. Trust is built incrementally.

### The Deeper Pattern

Elmer changes what a "session" means. Currently you open Claude Code, work, close it. With Elmer running continuously (Phase 3), Claude Code becomes the interactive layer for steering and review, while Elmer is the autonomous layer that runs between sessions. The two compose: you steer Elmer from within Claude Code, and Elmer spawns Claude Code sessions as workers.

The archetype library is a form of institutional memory. Which templates produce the best proposals? Which topics lead to productive chains? This is meta-learning about how to use AI effectively, accumulated across projects and time.

### Naming

Elmer Fudd. Persistent hunter. Homage to the [Ralph Wiggum](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) naming tradition for autonomous Claude Code tools. Ralph uses a Stop hook for iterative self-referential loops. Elmer uses git branches for parallel autonomous exploration. Different shapes, same lineage.

## Architecture

### Modules

| Module | Responsibility |
|--------|---------------|
| `cli.py` | Click CLI entry point, argument parsing |
| `explore.py` | Orchestration: create worktree, assemble prompt, spawn worker |
| `review.py` | Read proposals, display status and summaries |
| `gate.py` | Approve (merge) or reject (discard) explorations |
| `worktree.py` | Git worktree and branch operations |
| `worker.py` | Claude CLI invocation and process management |
| `state.py` | SQLite state tracking |
| `config.py` | Configuration loading and project initialization |
| `generate.py` | AI topic generation orchestration |
| `autoapprove.py` | AI review gate for auto-approval |
| `promptgen.py` | Two-stage AI prompt generation |
| `archselect.py` | AI archetype selection |
| `costs.py` | Cost reporting and summaries |
| `daemon.py` | Daemon loop, PID management, cycle execution |
| `insights.py` | Cross-project insight extraction and injection |
| `questions.py` | Question mining from project documentation |
| `scaffold.py` | Project scaffolding (five-document pattern) |
| `archstats.py` | Archetype effectiveness statistics |
| `invariants.py` | Document invariant enforcement |
| `dashboard.py` | Multi-project status aggregation |
| `pr.py` | PR creation via gh CLI |

### Data Flow

```
explore → slugify(topic)
        → create git worktree on branch elmer/<slug>
        → load archetype template, substitute $TOPIC
        → spawn claude -p in worktree (background, PID tracked)
        → record in SQLite

status  → for each running: check PID alive
        → if dead: check PROPOSAL.md exists → mark done or failed
        → display table

review  → read PROPOSAL.md from worktree

approve → git merge branch into current branch
        → remove worktree, delete branch
        → update SQLite

reject  → remove worktree, delete branch
        → update SQLite

clean   → remove worktrees/state for approved/rejected explorations
        → git worktree prune
```

### State Model

```
pending → running → done → approved
                        → rejected
                  → failed → rejected
```

- **pending**: Blocked by unmet dependencies (no worktree yet)
- **running**: Claude session active (PID alive)
- **done**: Session finished, PROPOSAL.md exists
- **failed**: Session finished, no PROPOSAL.md
- **approved**: Branch merged, worktree removed
- **rejected**: Branch deleted, worktree removed

### Storage

SQLite database at `.elmer/state.db`:

```sql
explorations (
    id TEXT PRIMARY KEY,       -- slug
    topic TEXT,                -- original topic text
    archetype TEXT,            -- template used
    branch TEXT,               -- git branch name
    worktree_path TEXT,        -- absolute path to worktree
    status TEXT,               -- pending|running|done|approved|rejected|failed
    model TEXT,                -- sonnet|opus|haiku
    pid INTEGER,               -- OS process ID
    created_at TEXT,           -- ISO timestamp
    completed_at TEXT,         -- ISO timestamp
    merged_at TEXT,            -- ISO timestamp
    proposal_summary TEXT,     -- first few lines of PROPOSAL.md
    parent_id TEXT,            -- what spawned this (for follow-ups)
    max_turns INTEGER,         -- turn limit for claude session
    auto_approve INTEGER DEFAULT 0, -- 1 = trigger AI review on completion
    on_approve TEXT,               -- shell command on approval ($ID, $TOPIC)
    on_reject TEXT                 -- shell command on rejection ($ID, $TOPIC)
)

dependencies (
    exploration_id TEXT,       -- the exploration that depends
    depends_on_id TEXT,        -- the exploration it depends on
    PRIMARY KEY (exploration_id, depends_on_id)
)
```

### Archetypes

Markdown templates with `$TOPIC` substitution. Resolved in order:
1. `.elmer/archetypes/<name>.md` (project-local, user-customizable)
2. Bundled `src/elmer/archetypes/<name>.md` (package defaults)

Exploration archetypes (8):
- **explore** — read-only analysis, no action bias
- **explore-act** — analysis biased toward concrete proposals
- **prototype** — write working code on the branch
- **adr-proposal** — propose architecture decisions
- **question-cluster** — explore clusters of related questions
- **benchmark** — measure and evaluate
- **dead-end-analysis** — analyze potential dead ends
- **devil-advocate** — challenge assumptions and decisions

Meta-prompt archetypes (7):
- **generate-topics** — meta-prompt for AI topic generation
- **prompt-gen** — meta-prompt for two-stage prompt generation
- **review-gate** — prompt for auto-approve AI review
- **select-archetype** — meta-prompt for AI archetype selection
- **extract-insights** — meta-prompt for insight extraction
- **mine-questions** — meta-prompt for question mining
- **validate-invariants** — meta-prompt for invariant enforcement

### Git Integration

- Each exploration creates a branch `elmer/<slug>` and a worktree at `.elmer/worktrees/<slug>/`
- Worktrees share the `.git` directory — instant creation, space-efficient
- Approve merges into whatever branch HEAD currently points to
- Reject deletes the branch and worktree
- Remote operations (`elmer pr`) available for GitHub integration via `gh` CLI

### Claude Invocation

```
claude -p "<assembled prompt>" --model <model> --max-turns <N>
```

Runs in the worktree directory. Claude reads project files (CLAUDE.md, etc.) from the worktree and can create/modify files there. The session runs as a background process (detached via `start_new_session`). Output captured to `.elmer/logs/<slug>.log`.

## Planned Architecture [Phase 2+]

### Daemon Loop

**Status: Implemented** — see `src/elmer/daemon.py`, `src/elmer/cli.py` (daemon command group)

```
┌──────────────────────────────────────────────────┐
│                 ELMER DAEMON                      │
│                                                   │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐      │
│  │GENERATE │───▶│SCHEDULE │───▶│  SPAWN  │      │
│  │ topics  │    │  (DAG)  │    │ workers │      │
│  └─────────┘    └─────────┘    └─────────┘      │
│       ▲              ▲              │             │
│       │              │              ▼             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐      │
│  │  LEARN  │◀───│  GATE   │◀───│HARVEST  │      │
│  │(feed DAG)│   │approve/ │    │proposals│      │
│  └─────────┘    │reject   │    └─────────┘      │
│                  └─────────┘                      │
└──────────────────────────────────────────────────┘
```

Each cycle: harvest completed → gate (auto/human) → merge approved → schedule unblocked → generate new topics (if below threshold). Interval-driven with cost budget per cycle.

### Exploration DAG

**Status: Implemented** — see `src/elmer/state.py` (dependencies table), `src/elmer/explore.py` (schedule_ready)

Explorations can depend on each other. An exploration only starts when all dependencies are approved and merged.

```
seed topic
├── exploration A (approved, merged)
│   ├── follow-up A1 (approved, merged)
│   │   └── follow-up A1a (running...)
│   └── follow-up A2 (rejected — dead end)
├── exploration B (approved, merged)
│   └── follow-up B1 (pending review)
└── exploration C (running...)
```

State model extends with:
```sql
ALTER TABLE explorations ADD COLUMN parent_id TEXT;  -- what spawned this
ALTER TABLE explorations ADD COLUMN project_path TEXT; -- multi-project

CREATE TABLE dependencies (
    exploration_id TEXT,
    depends_on_id TEXT,
    PRIMARY KEY (exploration_id, depends_on_id)
);
```

### Two-Stage Prompt Generation

Instead of static `$TOPIC` substitution:

1. **Stage 1 (meta):** `claude -p "Given this project and topic, generate the optimal exploration prompt"` — reads project docs, available archetypes, topic, produces a bespoke prompt
2. **Stage 2 (execution):** Execute the generated prompt in the worktree

The archetype becomes a hint to Stage 1, not a rigid template. Stage 1 can combine elements from multiple archetypes, add project-specific instructions, or generate entirely novel prompts.

### Auto-Approve Gate

**Status: Implemented** — see `src/elmer/autoapprove.py`, `src/elmer/archetypes/review-gate.md`

After exploration completes, if auto-approve is enabled:

1. Spawn a second `claude -p` session with the proposal and criteria
2. AI evaluates: "Does this proposal meet the approval criteria?"
3. Output: APPROVE or REJECT with reasoning
4. If APPROVE → auto-merge. If REJECT → queue for human review with reasoning attached.

Criteria configurable per-project in `.elmer/config.toml`.

### Cross-Project Architecture

**Status: Implemented** — see `src/elmer/insights.py`

```
~/.elmer/
├── insights.db          # Cross-project insight log (SQLite)

/path/to/project/.elmer/
├── config.toml          # Project-specific overrides
├── archetypes/          # Project-specific templates
├── state.db             # Project state
├── worktrees/
└── logs/
```

Insights extracted from explorations that are generalizable get stored in `~/.elmer/insights.db`. Future explorations in any project get relevant insights injected into their prompt context. Extraction is opt-in via `[insights] enabled = true`. Injection uses keyword-based relevance matching.

### Question Mining

**Status: Implemented** — see `src/elmer/questions.py`

`elmer mine-questions` runs a synchronous `claude -p` session that reads project documentation and extracts open questions — both explicit (marked as TODO, TBD) and implicit (gaps, missing strategies). Questions are clustered by theme. With `--spawn`, clusters are converted to exploration topics.

### Project Scaffolding

**Status: Implemented** — see `src/elmer/scaffold.py`

`elmer init --docs` scaffolds the five-document pattern (CLAUDE.md, DESIGN.md, DECISIONS.md, ROADMAP.md, CONTEXT.md) that makes projects effective with Claude Code. Templates are Python format strings in `scaffold.py` with `{project_name}` substitution. Only creates files that don't already exist — safe to run repeatedly.

### Template Evolution

**Status: Implemented** — see `src/elmer/archstats.py`

`elmer archetypes stats` shows archetype effectiveness metrics computed from existing exploration data: approval rate, rejection count, average cost, total explorations per archetype. `elmer archetypes list` shows all available archetypes (local + bundled). No new tables or tracking — everything is derived from the existing `explorations` table.

### Attention Routing

**Status: Implemented** — see `src/elmer/review.py` (`list_proposals_prioritized`, `_score_proposal`)

`elmer review --prioritize` ranks pending proposals using a deterministic heuristic: dependents blocked (+30 each), staleness (+1/hour, max 24), small diff (+10), failed status (+5). Scores and reasons are displayed to help humans review the most impactful proposals first. No AI call — fast, free, transparent.

### Document Invariant Enforcement

**Status: Implemented** — see `src/elmer/invariants.py`, `src/elmer/archetypes/validate-invariants.md`

`elmer validate` and `elmer approve --validate-invariants` spawn a synchronous `claude -p` session that checks document consistency (ADR counts, phase status, feature claims) and auto-fixes violations. Default rules match CLAUDE.md's "Document Invariants" section. Custom rules configurable in `[invariants] rules` in `config.toml`.

### Multi-Project Dashboard

**Status: Implemented** — see `src/elmer/dashboard.py`, `src/elmer/config.py` (registry functions)

`elmer status --all-projects` aggregates exploration status across all registered Elmer projects. Projects are tracked in a global registry at `~/.elmer/projects.json`, automatically updated when `elmer init` runs or any command accesses `.elmer/`. The dashboard shows counts by status and total cost per project with a grand totals row when multiple projects are registered. Stale registry entries are pruned on read.

### PR-Based Review

**Status: Implemented** — see `src/elmer/pr.py`

`elmer pr ID` pushes an exploration branch to the remote and creates a GitHub PR using the `gh` CLI. PROPOSAL.md content becomes the PR body. This integrates Elmer with existing code review workflows — explorations can be reviewed and discussed via GitHub's PR interface instead of (or in addition to) the local `elmer review` / `elmer approve` flow. The `gh` CLI is an optional dependency.

## Design Decisions

Full rationale in DECISIONS.md. Summary:

- **ADR-001:** Git worktrees over directory copying
- **ADR-002:** Background `claude -p` over Agent Teams
- **ADR-003:** SQLite over JSON state files
- **ADR-004:** Click over argparse
- **ADR-005:** Static templates before generated prompts
- **ADR-006:** No daemon in Phase 1
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

*Last updated: Phase 4 complete — all features implemented*
