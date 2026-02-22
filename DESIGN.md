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
running → done → approved
              → rejected
        → failed → rejected
```

- **running**: Claude session active (PID alive)
- **done**: Session finished, PROPOSAL.md exists
- **failed**: Session finished, no PROPOSAL.md
- **approved**: Branch merged, worktree removed
- **rejected**: Branch deleted, worktree removed

### Storage

SQLite database at `.elmer/state.db`. Single table:

```sql
explorations (
    id TEXT PRIMARY KEY,       -- slug
    topic TEXT,                -- original topic text
    archetype TEXT,            -- template used
    branch TEXT,               -- git branch name
    worktree_path TEXT,        -- absolute path to worktree
    status TEXT,               -- running|done|approved|rejected|failed
    model TEXT,                -- sonnet|opus|haiku
    pid INTEGER,               -- OS process ID
    created_at TEXT,           -- ISO timestamp
    completed_at TEXT,         -- ISO timestamp
    merged_at TEXT,            -- ISO timestamp
    proposal_summary TEXT      -- first few lines of PROPOSAL.md
)
```

### Archetypes

Markdown templates with `$TOPIC` substitution. Resolved in order:
1. `.elmer/archetypes/<name>.md` (project-local, user-customizable)
2. Bundled `src/elmer/archetypes/<name>.md` (package defaults)

Three bundled archetypes:
- **explore** — read-only analysis, no action bias
- **explore-act** — analysis biased toward concrete proposals
- **prototype** — write working code on the branch

### Git Integration

- Each exploration creates a branch `elmer/<slug>` and a worktree at `.elmer/worktrees/<slug>/`
- Worktrees share the `.git` directory — instant creation, space-efficient
- Approve merges into whatever branch HEAD currently points to
- Reject deletes the branch and worktree
- No remote operations (push/PR) in Phase 1

### Claude Invocation

```
claude -p "<assembled prompt>" --model <model> --max-turns <N>
```

Runs in the worktree directory. Claude reads project files (CLAUDE.md, etc.) from the worktree and can create/modify files there. The session runs as a background process (detached via `start_new_session`). Output captured to `.elmer/logs/<slug>.log`.

## Planned Architecture [Phase 2+]

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

Each cycle: harvest completed → gate (auto/human) → merge approved → schedule unblocked → generate new topics (if below threshold). Interval-driven with cost budget per cycle.

### Exploration DAG

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

After exploration completes, if auto-approve is enabled:

1. Spawn a second `claude -p` session with the proposal and criteria
2. AI evaluates: "Does this proposal meet the approval criteria?"
3. Output: APPROVE or REJECT with reasoning
4. If APPROVE → auto-merge. If REJECT → queue for human review with reasoning attached.

Criteria configurable per-project in `.elmer/config.toml`.

### Cross-Project Architecture

```
~/.elmer/
├── config.toml          # Global config (default model, budget)
├── insights.db          # Cross-project insight log
└── projects.toml        # Registered projects (optional)

/path/to/project/.elmer/
├── config.toml          # Project-specific overrides
├── archetypes/          # Project-specific templates
├── state.db             # Project state
├── worktrees/
└── logs/
```

Insights extracted from explorations that are generalizable get stored in `~/.elmer/insights.db`. Future explorations in any project get relevant insights injected into their prompt context.

## Design Decisions

Full rationale in DECISIONS.md. Summary:

- **ADR-001:** Git worktrees over directory copying
- **ADR-002:** Background `claude -p` over Agent Teams
- **ADR-003:** SQLite over JSON state files
- **ADR-004:** Click over argparse
- **ADR-005:** Static templates before generated prompts
- **ADR-006:** No daemon in Phase 1

*Last updated: Phase 1*
