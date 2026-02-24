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
        │  APPROVE   │  │  DECLINE  │
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
| `gate.py` | Approve (merge) or decline (discard) explorations |
| `worktree.py` | Git worktree and branch operations |
| `worker.py` | Claude CLI invocation, process management, agent flag building |
| `state.py` | SQLite state tracking |
| `config.py` | Configuration loading, project initialization, agent resolution |
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
| `mcp_server.py` | MCP server — structured tool access over stdio |

### Data Flow

```
explore → slugify(topic)
        → create git worktree on branch elmer/<slug>
        → resolve agent (config.resolve_agent) or load template
        → spawn claude -p --agents/--agent in worktree (background, PID tracked)
        → record in SQLite

status  → for each running: check PID alive
        → if dead: check PROPOSAL.md exists → mark done or failed
        → display table

review  → read PROPOSAL.md from worktree

approve → git merge branch into current branch
        → remove worktree, delete branch
        → update SQLite

decline → remove worktree, delete branch
        → update SQLite

clean   → remove worktrees/state for approved/declined explorations
        → git worktree prune
```

### State Model

```
pending → running → done → approved
                        → declined
                  → failed → declined
```

- **pending**: Blocked by unmet dependencies (no worktree yet)
- **running**: Claude session active (PID alive)
- **done**: Session finished, PROPOSAL.md exists
- **failed**: Session finished, no PROPOSAL.md in worktree. Failure reason diagnosed from session log (wrong write path, claude error, permission denials, or normal completion without output).
- **approved**: Branch merged, worktree removed
- **declined**: Branch deleted, worktree removed

### Proposal Archive

Proposals are archived to `.elmer/proposals/<id>.md` before worktree cleanup on approve, decline, cancel, retry, and clean. Each archived file includes a metadata header (HTML comment) with exploration ID, topic, archetype, model, final status, and archive timestamp. The archive is best-effort — failures never block the flow.

This makes proposals persistent, independent of the branch lifecycle. Approved proposals survive merge-and-cleanup. Declined proposals preserve institutional knowledge about rejected approaches.

### Failure Diagnosis

When an exploration transitions to `failed`, the session log at `.elmer/logs/<id>.log` is parsed for structured diagnostics:

- **is_error**: Whether claude reported a session error
- **result text**: Claude's final response — reveals if PROPOSAL.md was written to the wrong path
- **permission_denials**: Tool calls that were denied (sandboxing conflicts)
- **turn count**: How many turns were used vs max_turns

`elmer logs ID` displays the full parsed diagnostic. Failure reasons are stored in the `proposal_summary` field with structured categories rather than the generic "(no PROPOSAL.md produced)".

### Storage

SQLite database at `.elmer/state.db`:

```sql
explorations (
    id TEXT PRIMARY KEY,       -- slug
    topic TEXT,                -- original topic text
    archetype TEXT,            -- template used
    branch TEXT,               -- git branch name
    worktree_path TEXT,        -- absolute path to worktree
    status TEXT,               -- pending|running|done|approved|declined|failed
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
    on_decline TEXT                -- shell command on declining ($ID, $TOPIC)
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

### Archetypes & Agents

Archetypes define exploration methodology. Two invocation modes (ADR-026):

**Agent mode** (preferred): Archetype is a Claude Code custom subagent definition — markdown with YAML frontmatter (`name`, `description`, `tools`, optional `model`). The agent's system prompt provides methodology; the `-p` prompt provides the topic. Invoked via `--agents` inline JSON + `--agent` flags.

**Template mode** (fallback): Markdown templates with `$TOPIC` substitution. Used when no agent definition exists.

Agent resolution order:
1. `.claude/agents/elmer-<name>.md` (project-local, scaffolded via `elmer init --agents`)
2. Bundled `src/elmer/agents/<name>.md` (package defaults)
3. `.elmer/archetypes/<name>.md` (template fallback)
4. Bundled `src/elmer/archetypes/<name>.md` (template fallback)

Meta-operation agent resolution uses `elmer-meta-<name>` prefix.

Exploration archetypes (8): explore, explore-act, prototype, adr-proposal, question-cluster, benchmark, dead-end-analysis, devil-advocate. Action archetypes (explore-act, prototype, adr-proposal, benchmark) have `Edit, Write`; analysis archetypes (explore, question-cluster, dead-end-analysis, devil-advocate) have `Write` only. All have `Read, Grep, Glob, Bash`.

Audit archetypes (8): consistency-audit, coherence-audit, architecture-audit, operational-audit, documentation-audit, opportunity-scan, workflow-audit, mission-audit. Tools: `Read, Grep, Glob, Bash, Write`.

Meta-operation agents (7): generate-topics, prompt-gen, review-gate, select-archetype, extract-insights, mine-questions, validate-invariants. Model: `sonnet`.

### Git Integration

- Each exploration creates a branch `elmer/<slug>` and a worktree at `.elmer/worktrees/<slug>/`
- Worktrees share the `.git` directory — instant creation, space-efficient
- Approve merges into whatever branch HEAD currently points to
- Decline deletes the branch and worktree
- Remote operations (`elmer pr`) available for GitHub integration via `gh` CLI

### Claude Invocation

Two invocation patterns, both agent-aware (ADR-026):

- **Background** (`spawn_claude`): Explorations. Long-running, PID-tracked, output to `.elmer/logs/<slug>.log`. Runs in worktree directory. Agent config passed via `--agents` inline JSON + `--agent` flags.
- **Synchronous** (`run_claude`): Meta-operations (topic generation, auto-approve, prompt generation, archetype selection, insight extraction, question mining, invariant validation). Short-lived (3-5 turns), output parsed immediately by caller.

Both use `claude [--agents JSON --agent name] -p <prompt> --output-format json --model <model> --max-turns <N>`. When an agent config specifies a model, the `--model` flag is omitted to avoid conflict.

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
│  └─────────┘    │decline  │    └─────────┘      │
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
│   └── follow-up A2 (declined — dead end)
├── exploration B (approved, merged)
│   └── follow-up B1 (pending review)
└── exploration C (running...)
```

`--on-approve` / `--on-decline` chain actions execute user-specified shell commands with `$ID` and `$TOPIC` substitution (ADR-012). `--auto-followup` generates follow-up topics post-merge via `generate_topics()`.

### Two-Stage Prompt Generation

Instead of static `$TOPIC` substitution:

1. **Stage 1 (meta):** Synchronous `claude -p` reads project docs, available archetypes, and topic — produces a bespoke prompt
2. **Stage 2 (execution):** Execute the generated prompt in the worktree

The archetype becomes a hint to Stage 1, not a rigid template. Fallback: static templates when `--generate-prompt` is not used.

### Auto-Approve Gate

After exploration completes, if `--auto-approve` is set:

1. Synchronous `claude -p` evaluates the proposal against configurable criteria
2. Output: APPROVE or REJECT verdict with reasoning (AI protocol intentionally retains REJECT — user-facing terminology uses "decline")
3. If APPROVE → auto-merge. If REJECT → queue for human review with reasoning attached (status becomes "done", not auto-declined).

Conservative default: decline when uncertain. Criteria configurable in `.elmer/config.toml`.

### Attention Routing

`elmer review --prioritize` ranks proposals using a deterministic heuristic scoring function. Scoring factors: dependents blocked (+30 per blocker), staleness (+1 per hour, max 24), diff size (small = +10), failed status (+5). Scores and reasons are displayed. No API call required.

### Cross-Project Layout

```
~/.elmer/
├── insights.db          # Cross-project insight log (SQLite)
├── projects.json        # Global project registry

/path/to/project/.elmer/
├── config.toml          # Project-specific overrides
├── archetypes/          # Project-specific templates (fallback)
├── state.db             # Project state
├── proposals/           # Archived PROPOSAL.md files (persistent)
├── worktrees/
└── logs/

/path/to/project/.claude/agents/
├── elmer-explore-act.md # Project-local agent overrides (optional)
├── elmer-meta-*.md      # Meta-operation agent overrides
└── ...                  # Scaffolded via elmer init --agents
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

### MCP Server

`mcp_server.py` exposes Elmer state and operations as MCP tools over stdio JSON-RPC (ADR-024). Started via `elmer mcp`. Uses Anthropic's `mcp` Python SDK (FastMCP). 17 tools total.

**Read-only tools (6):**

| Tool | Wraps | Returns |
|------|-------|---------|
| `elmer_status` | `state.list_explorations()` | Explorations + status summary |
| `elmer_review` | `state.get_exploration()` + PROPOSAL.md | Proposal list (with optional prioritization) or full proposal content + metadata + dependencies |
| `elmer_costs` | `state.list_explorations()` + `state.get_all_costs()` | Cost data per exploration + meta-ops + totals |
| `elmer_tree` | `state.list_explorations()` + `state.get_dependencies()` | Recursive dependency tree |
| `elmer_archetypes` | `config.ARCHETYPES_DIR` glob + optional stats | Archetype list with optional approval rates |
| `elmer_insights` | `insights.list_all_insights()` / `get_relevant_insights()` | Cross-project insights |

**Mutation tools (7):**

| Tool | Wraps | Effect |
|------|-------|--------|
| `elmer_explore` | `explore.start_exploration()` | Creates branch, spawns background claude session. Supports auto-archetype, two-stage prompt generation, chain actions. |
| `elmer_approve` | `gate.approve_exploration()` / `gate.approve_all()` | Merges branch, cleans up, unblocks dependents. Supports approve-all, auto-followup, invariant validation. |
| `elmer_decline` | `gate.decline_exploration()` | Deletes branch and worktree |
| `elmer_cancel` | `gate.cancel_exploration()` | Stops process, deletes branch and worktree |
| `elmer_retry` | `gate.retry_exploration()` / `gate.retry_all_failed()` | Re-spawns failed explorations with same parameters |
| `elmer_clean` | `gate.clean_all()` | Removes worktrees/state for finished explorations |
| `elmer_pr` | `pr.create_pr_for_exploration()` | Pushes branch, creates GitHub PR via gh CLI |

**Intelligence tools (3):**

| Tool | Wraps | Effect |
|------|-------|--------|
| `elmer_generate` | `generate.generate_topics()` + optional spawn | AI topic generation from project context. Optionally spawns explorations. |
| `elmer_validate` | `invariants.validate_invariants()` | Document invariant checking with auto-fix |
| `elmer_mine_questions` | `questions.mine_questions()` + optional spawn | Extracts open questions from docs. Optionally spawns explorations. |

**Batch tool (1):**

| Tool | Wraps | Effect |
|------|-------|--------|
| `elmer_batch` | `explore.start_exploration()` loop | Multiple explorations from a structured topic list. Supports chaining and concurrency limits. |

Each tool opens a DB connection per call, matching the CLI pattern. Mutation tools catch `SystemExit` from gate functions (which use `sys.exit(1)` for validation errors) and convert to structured error responses.

## Design Decisions

10 ADRs recorded. Full rationale and domain index in DECISIONS.md.

*Last updated: 2026-02-23, added proposal archive, failure diagnosis, `elmer logs` command*
