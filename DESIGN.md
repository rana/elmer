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

## Why Elmer Exists

Two observations:

1. **Claude Code sessions are powerful but ephemeral.** Research insights, design proposals, and exploratory work die with the session unless manually preserved. Elmer makes exploration persistent — branches survive sessions, proposals accumulate, research trees grow across days.

2. **Multiple projects share a cognition pattern.** The five-document structure (CONTEXT.md, DESIGN.md, DECISIONS.md, ROADMAP.md, CLAUDE.md) works across projects. Elmer operationalizes this pattern — it reads those documents for context, explores topics autonomously, and produces proposals that fit the project's existing structure.

Elmer changes what a "session" means. Claude Code is the interactive layer for steering and review. Elmer is the autonomous layer that runs between sessions. You steer Elmer from Claude Code, and Elmer spawns Claude Code sessions as workers.

## Architecture

### Modules

| Module | Responsibility |
|--------|---------------|
| `cli.py` | Click CLI entry point, argument parsing |
| `explore.py` | Orchestration: create worktree, assemble prompt, spawn worker |
| `review.py` | Read proposals, display status, attention routing |
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
| `skill_scaffold.py` | Claude Code skill scaffolding |
| `archstats.py` | Archetype effectiveness statistics |
| `invariants.py` | Document invariant enforcement |
| `dashboard.py` | Multi-project status aggregation |
| `batch.py` | Topic list file parsing for batch command |
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

costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exploration_id TEXT,        -- NULL for standalone meta-operations
    operation TEXT NOT NULL,    -- generate|auto_approve|prompt_gen|archetype_select|...
    model TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    created_at TEXT NOT NULL
)

daemon_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_number INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    harvested INTEGER DEFAULT 0,
    approved INTEGER DEFAULT 0,
    scheduled INTEGER DEFAULT 0,
    generated INTEGER DEFAULT 0,
    audits INTEGER DEFAULT 0,
    cycle_cost_usd REAL,
    error TEXT
)
```

### Archetypes

Markdown templates with `$TOPIC` substitution. Resolved in order:
1. `.elmer/archetypes/<name>.md` (project-local, user-customizable)
2. Bundled `src/elmer/archetypes/<name>.md` (package defaults)

Exploration archetypes (8): explore, explore-act, prototype, adr-proposal, question-cluster, benchmark, dead-end-analysis, devil-advocate.

Audit archetypes (8): consistency-audit, coherence-audit, architecture-audit, operational-audit, documentation-audit, opportunity-scan, workflow-audit, mission-audit.

Meta-prompt archetypes (7): generate-topics, prompt-gen, review-gate, select-archetype, extract-insights, mine-questions, validate-invariants.

### Git Integration

- Each exploration creates a branch `elmer/<slug>` and a worktree at `.elmer/worktrees/<slug>/`
- Worktrees share the `.git` directory — instant creation, space-efficient
- Approve merges into whatever branch HEAD currently points to
- Reject deletes the branch and worktree
- Remote operations (`elmer pr`) available for GitHub integration via `gh` CLI

### Claude Invocation

Two invocation patterns:

- **Background** (`spawn_claude`): Explorations. Long-running, PID-tracked, output to `.elmer/logs/<slug>.log`. Runs in worktree directory.
- **Synchronous** (`run_claude`): Meta-operations (topic generation, auto-approve, prompt generation, archetype selection, insight extraction, question mining, invariant validation). Short-lived (3-5 turns), output parsed immediately by caller.

Both use `claude -p --output-format json --model <model> --max-turns <N>`.

### Daemon Loop

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

The daemon calls existing functions in a loop — no new execution model (ADR-010). Each cycle: harvest completed → gate (auto/human) → merge approved → schedule unblocked → generate new topics. Interval-driven with cost budget per cycle. PID file at `.elmer/daemon.pid` for single-instance enforcement.

### Exploration DAG

Explorations can depend on each other via the `dependencies` table. An exploration only starts when all dependencies are approved and merged.

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

`--on-approve` / `--on-reject` chain actions execute user-specified shell commands with `$ID` and `$TOPIC` substitution (ADR-012). `--auto-followup` generates follow-up topics post-merge via `generate_topics()`.

### Two-Stage Prompt Generation

Instead of static `$TOPIC` substitution:

1. **Stage 1 (meta):** Synchronous `claude -p` reads project docs, available archetypes, and topic — produces a bespoke prompt
2. **Stage 2 (execution):** Execute the generated prompt in the worktree

The archetype becomes a hint to Stage 1, not a rigid template. Fallback: static templates when `--generate-prompt` is not used.

### Auto-Approve Gate

After exploration completes, if `--auto-approve` is set:

1. Synchronous `claude -p` evaluates the proposal against configurable criteria
2. Output: APPROVE or REJECT with reasoning
3. If APPROVE → auto-merge. If REJECT → queue for human review with reasoning attached.

Conservative default: reject when uncertain. Criteria configurable in `.elmer/config.toml`.

### Cross-Project Layout

```
~/.elmer/
├── insights.db          # Cross-project insight log (SQLite)
├── projects.json        # Global project registry

/path/to/project/.elmer/
├── config.toml          # Project-specific overrides
├── archetypes/          # Project-specific templates
├── state.db             # Project state
├── worktrees/
└── logs/
```

Insights extracted from approved proposals get stored in `~/.elmer/insights.db`. Future explorations get relevant insights injected via keyword matching. Extraction is opt-in (`[insights] enabled = true`). Both extraction and injection are best-effort — failures never block the flow.

### Elmer vs Claude Code Skills

Elmer archetypes and Claude Code skills overlap in analysis methodology but serve different moments:

| Dimension | Elmer archetypes | Claude Code skills |
|-----------|-----------------|-------------------|
| Execution | Background `claude -p` on git branches | Interactive, in-session |
| Output | PROPOSAL.md on a branch | Action list in chat |
| State | Tracked in SQLite, persistent | Ephemeral, dies with session |
| Best for | Autonomous batch research, overnight runs | Interactive design thinking, quick audits |

The overlap is tolerated. No shared template layer — they diverge independently because they serve different runtimes. `elmer init --skills` generates project-specific skills from doc signals.

## Design Decisions

23 ADRs recorded. Full rationale and domain index in DECISIONS.md.

*Last updated: 2026-02-23, crystallization — merged architecture sections, removed duplication*
