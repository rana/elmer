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
