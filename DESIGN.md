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
| `config.py` | Configuration loading, project initialization, agent resolution, IDE watcher exclusion |
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
| `digest.py` | Convergence digest synthesis from exploration history |
| `synthesize.py` | Ensemble synthesis — consolidate multiple proposals on the same topic |
| `implement.py` | Milestone decomposition, cross-step context, plan loading, autonomous implementation orchestration |
| `mcp_server.py` | MCP server — structured tool access over stdio |

### Data Flow

```
explore → slugify(topic)
        → create git worktree on branch elmer/<slug>
        → resolve agent (config.resolve_agent) or load template
        → spawn claude -p --agents/--agent in worktree (background, PID tracked)
        → record in SQLite

status  → for each running/amending: check PID alive
        → if dead: check PROPOSAL.md exists → mark done or failed
        → display table

review  → read PROPOSAL.md from worktree

amend   → read current PROPOSAL.md
        → spawn claude -p with amend agent + editorial feedback in existing worktree
        → mark status amending → done when finished

approve → git merge branch into current branch
        → archive PROPOSAL.md to .elmer/proposals/<id>.md
        → remove worktree, delete branch
        → delete SQLite record (archive is permanent record — ADR-032)

decline → archive PROPOSAL.md to .elmer/proposals/<id>.md
        → remove worktree, delete branch
        → delete SQLite record (decline_reason preserved in archive)

digest  → read approved/declined proposals from .elmer/proposals/ (archive metadata)
        → merge with in-flight DB records
        → read previous digest from .elmer/digests/
        → run claude -p with digest meta-agent (synchronous)
        → store result in .elmer/digests/

implement → decompose milestone via meta-agent (opus, reads project docs)
          → present plan + questions to user (or --dry-run)
          → inject user answers into step topics
          → create chained explorations with verify_cmd and plan_id
          → daemon/scheduler executes steps in dependency order
          → verification hooks auto-amend on failure (ADR-038)
          → plan completes when all steps approved

clean   → remove worktrees/state for failed/orphaned explorations
        → git worktree prune
```

### State Model

```
pending → running → done → approved
                        → declined
                        → amending → done
                  → [verify] → amending → done (auto-amend on failure, ADR-038)
                  → failed → declined
                           → amending → done
```

- **pending**: Blocked by unmet dependencies (no worktree yet)
- **running**: Claude session active (PID alive)
- **[verify]**: If `verify_cmd` is set (per-exploration or global), runs after PROPOSAL.md commit. On pass → done. On fail → auto-amend (up to `max_retries`), then failed.
- **done**: Session finished, PROPOSAL.md exists, verification passed (if applicable)
- **amending**: Revision session active — triggered by editorial feedback (`elmer amend`) or verification failure (auto-amend). Transitions back to `done` when finished, re-triggering verification if applicable.
- **failed**: Session finished without PROPOSAL.md, or verification exhausted max retries. If part of a plan, the plan is paused.
- **approved**: Branch merged, worktree removed
- **declined**: Branch deleted, worktree removed

### Proposal Archive

The archive at `.elmer/proposals/<id>.md` is the source of truth for completed explorations (ADR-032). Each file includes a self-describing metadata header (HTML comment) with exploration ID, topic, archetype, model, final status, merged_at, completed_at, decline_reason, and archive timestamp. The archive is best-effort — failures never block the flow.

Approve and decline auto-clean DB records after archiving. The database tracks only in-flight state; the archive is the permanent record. Slug uniqueness checks both DB and archive to prevent overwrites after clean. Digest synthesis reads archive metadata directly, so it works regardless of DB state.

`clean` is now a garbage collector for failed explorations and crash recovery, not a required workflow step.

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
    on_decline TEXT,               -- shell command on declining ($ID, $TOPIC)
    decline_reason TEXT,           -- why it was declined (feeds digest synthesis)
    verify_cmd TEXT,               -- shell command to verify before done (ADR-038)
    plan_id TEXT,                  -- implementation plan this step belongs to (ADR-039)
    plan_step INTEGER,             -- step index within the plan
    amend_count INTEGER DEFAULT 0  -- auto-amend attempts for verification
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

plans (
    id TEXT PRIMARY KEY,           -- slug from milestone_ref
    milestone_ref TEXT NOT NULL,   -- original milestone text
    status TEXT NOT NULL DEFAULT 'active',  -- active|completed|paused
    plan_json TEXT NOT NULL,       -- full decomposition output (JSON)
    created_at TEXT NOT NULL,
    completed_at TEXT,
    total_cost_usd REAL DEFAULT 0
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
    digests INTEGER DEFAULT 0,
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

Exploration archetypes (9): explore, explore-act, prototype, implement, adr-proposal, question-cluster, benchmark, dead-end-analysis, devil-advocate. Action archetypes (explore-act, prototype, implement, adr-proposal, benchmark) have `Edit, Write`; analysis archetypes (explore, question-cluster, dead-end-analysis, devil-advocate) have `Write` only. All have `Read, Grep, Glob, Bash`.

Audit archetypes (8): consistency-audit, coherence-audit, architecture-audit, operational-audit, documentation-audit, opportunity-scan, workflow-audit, mission-audit. Tools: `Read, Grep, Glob, Bash, Write`.

Meta-operation agents (11): generate-topics, prompt-gen, review-gate, select-archetype, extract-insights, mine-questions, validate-invariants, amend, digest, synthesize, decompose. Model: `sonnet` (except decompose which uses `opus` for deep architectural reasoning). The amend agent has `Read, Grep, Glob, Bash, Edit, Write` for editorial revision. The digest agent synthesizes convergence across approved/declined proposals. The decompose agent reads project docs and produces structured JSON implementation plans (ADR-039).

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

The daemon calls existing functions in a loop — no new execution model (ADR-010). Each cycle: harvest completed → gate (auto/human) → merge approved → schedule unblocked → digest (if threshold met) → generate new topics. The digest step creates a two-timescale system: fast loop (explore → approve) and slow loop (digest → generate → explore). Interval-driven with cost budget per cycle. PID file at `.elmer/daemon.pid` for single-instance enforcement.

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
├── digests/             # Convergence digest files (timestamped)
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

`mcp_server.py` exposes Elmer state and operations as MCP tools over stdio JSON-RPC (ADR-024). Started via `elmer mcp`. Uses Anthropic's `mcp` Python SDK (FastMCP). 23 tools total.

**Read-only tools (8):**

| Tool | Wraps | Returns |
|------|-------|---------|
| `elmer_status` | `state.list_explorations()` + `worker.is_running()` | Explorations + status summary. Running/amending explorations include progress indicators (elapsed_minutes, pid_alive, log_bytes). |
| `elmer_review` | `state.get_exploration()` + PROPOSAL.md | Proposal list (with optional prioritization) or full proposal content + metadata + dependencies |
| `elmer_costs` | `state.list_explorations()` + `state.get_all_costs()` | Cost data per exploration + meta-ops + totals |
| `elmer_tree` | `state.list_explorations()` + `state.get_dependencies()` | Recursive dependency tree |
| `elmer_archetypes` | `config.ARCHETYPES_DIR` glob + optional stats | Archetype list with optional approval rates |
| `elmer_insights` | `insights.list_all_insights()` / `get_relevant_insights()` | Cross-project insights |
| `elmer_config_get` | `config.load_config()` | Full config or specific key via dot notation |
| `elmer_recover_partial` | Worktree glob for `*.md` | Partial artifacts from failed/active explorations. Content previews for salvaging work. |

**Mutation tools (8):**

| Tool | Wraps | Effect |
|------|-------|--------|
| `elmer_explore` | `explore.start_exploration()` | Creates branch, spawns background claude session. Supports auto-archetype, two-stage prompt generation, chain actions. |
| `elmer_approve` | `gate.approve_exploration()` / `gate.approve_all()` | Merges branch, cleans up, unblocks dependents. Skips merge if branch already merged (crash recovery). Sleeps between cascade worktree removals to avoid IDE inotify storms. Supports approve-all, auto-followup, invariant validation. |
| `elmer_decline` | `gate.decline_exploration()` | Deletes branch and worktree. Accepts optional decline reason. |
| `elmer_amend` | `explore.amend_exploration()` / `explore.preview_amend_prompt()` | Spawns revision session in existing worktree to revise PROPOSAL.md based on editorial feedback. `dry_run=true` returns prompt without spawning. |
| `elmer_cancel` | `gate.cancel_exploration()` | Stops process, deletes branch and worktree |
| `elmer_retry` | `gate.retry_exploration()` / `gate.retry_all_failed()` | Re-spawns failed explorations with same parameters |
| `elmer_clean` | `gate.clean_all()` / `gate.clean_preview()` | Removes worktrees/state for finished explorations. `preview=true` shows what would be cleaned without executing. |
| `elmer_pr` | `pr.create_pr_for_exploration()` | Pushes branch, creates GitHub PR via gh CLI |

**Intelligence tools (4):**

| Tool | Wraps | Effect |
|------|-------|--------|
| `elmer_generate` | `generate.generate_topics()` + optional spawn | AI topic generation from project context. Digest-aware — reads latest digest for directed generation. Returns digest metadata when available. |
| `elmer_validate` | `invariants.validate_invariants()` | Document invariant checking with auto-fix. `preview=true` reports violations without applying fixes. |
| `elmer_mine_questions` | `questions.mine_questions()` + optional spawn | Extracts open questions from docs. Optionally spawns explorations. |
| `elmer_digest` | `digest.run_digest()` | Synthesizes convergence digest from approved/declined proposals. Optional time and topic filters. |

**Implementation tools (2):**

| Tool | Wraps | Effect |
|------|-------|--------|
| `elmer_implement` | `implement.decompose_milestone()` + `execute_plan()` | Decompose milestone into steps, optionally execute. Supports dry_run. |
| `elmer_plan_status` | `implement.get_plan_status()` | Plan progress with per-step status and cost. |

**Batch tool (1):**

| Tool | Wraps | Effect |
|------|-------|--------|
| `elmer_batch` | `explore.start_exploration()` loop | Multiple explorations from a structured topic list. Supports chaining, concurrency limits, and stagger delays. |

Each tool opens a DB connection per call, matching the CLI pattern. Mutation tools catch `SystemExit` from gate functions (which use `sys.exit(1)` for validation errors) and convert to structured error responses.

**MCP Design Principles:**

- **MCP tools don't have special powers.** Every tool wraps a core module function (`state.py`, `explore.py`, `gate.py`, etc.). New capabilities belong in the core engine first, then get exposed via both CLI and MCP. The MCP is a presentation layer, not a privileged API.
- **State is data, not server memory.** The MCP server is stateless — each tool call opens a DB connection, queries, closes, and returns JSON. Any persistent state lives on disk (SQLite, archive files, digest files), never in server process memory.
- **Value density over feature count.** When evaluating tool additions, the metric is value delivered per unit of complexity added. Small high-impact changes (preview modes, parameter parity with CLI) compound. Large niche features (workflow engines, semantic layers) fragment.

## Design Decisions

25 ADRs recorded. Full rationale and domain index in DECISIONS.md.

*Last updated: 2026-02-25, ADR-042 prerequisites, artifact flow, greenfield decomposition (23 tools)*
