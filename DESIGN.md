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

### ADR-001: Git Worktrees Over Directory Copying

Worktrees share `.git`, are instant to create, and space-efficient. Directory copying wastes disk, duplicates git history, and creates confusion about which copy is canonical. Worktrees provide real branch isolation with minimal overhead.

### ADR-002: Background Processes Over Agent Teams

Agent teams are session-scoped and don't persist across Claude Code sessions. Elmer explorations should outlive any single session — start explorations, close your terminal, review tomorrow. Background `claude -p` processes provide this persistence.

### ADR-003: SQLite Over JSON State Files

Concurrent explorations writing to a single JSON file risk corruption. SQLite handles concurrent access correctly via WAL mode. It also supports queries (find all explorations by status) without loading everything into memory.

### ADR-004: Click Over Argparse

Click produces cleaner subcommand handling, better help text, and composable decorators. The single dependency is worth the ergonomic improvement for a CLI tool.

### ADR-005: Static Templates Before Generated Prompts

Phase 1 uses static archetype templates with `$TOPIC` substitution. Two-stage prompt generation (AI generates the prompt, then AI executes it) is deferred to Phase 2. Static templates are debuggable, predictable, and sufficient for initial use.

### ADR-006: No Daemon in Phase 1

The daemon (continuous loop: generate topics → spawn explorations → harvest → gate) adds complexity and requires cost controls. Phase 1 proves the core loop manually. If the manual loop is useful, the daemon is justified in Phase 2.

*Last updated: Phase 1*
