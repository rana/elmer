# Elmer — Decisions

Architecture Decision Records. Mutable living documents — update directly when decisions evolve. When substantially revising an ADR, add `*Revised: [date], [reason]*` at the section's end. Git history serves as the full audit trail.

25 ADRs recorded.

## Domain Index

| ADR | Domain | Summary |
|-----|--------|---------|
| ADR-001 | Git | Worktrees over directory copying |
| ADR-002 | Process | Background `claude -p` over Agent Teams |
| ADR-003 | Storage | SQLite over JSON state files |
| ADR-004 | CLI | Click over argparse |
| ADR-005 | Prompts | Static templates before generated prompts |
| ADR-006 | Architecture | Daemon deferred to Phase 3 |
| ADR-007 | Process | Synchronous `claude -p` for meta-operations |
| ADR-008 | Process | JSON output format for cost extraction |
| ADR-009 | Prompts | AI archetype selection as a meta-operation |
| ADR-010 | Architecture | Daemon as composition layer |
| ADR-011 | Process | PID file for daemon coordination |
| ADR-012 | Autonomy | Chain actions as shell commands |
| ADR-013 | Storage | Global insights database at ~/.elmer/ |
| ADR-014 | Prompts | Question mining as meta-operation |
| ADR-015 | Scaffolding | Five-document scaffolding as templates |
| ADR-016 | Analytics | Archetype stats from existing exploration data |
| ADR-017 | Review | Heuristic attention routing |
| ADR-018 | Validation | Invariant enforcement as meta-operation |
| ADR-019 | Storage | Global project registry for multi-project dashboard |
| ADR-020 | Integration | PR creation via gh CLI |
| ADR-021 | CLI | Topic list files with batch command |
| ADR-022 | Integration | Claude Code skill scaffolding as Elmer feature |
| ADR-023 | Governance | Mutable ADRs with git audit trail |
| ADR-024 | Integration | MCP server for structured tool access |
| ADR-025 | Scaffolding | Event-driven document maintenance in scaffolding |

---

## ADR-001: Git Worktrees Over Directory Copying

**Decision:** Use git worktrees for branch isolation, not directory copying.

Worktrees share `.git`, are instant to create, and space-efficient. Directory copying wastes disk, duplicates git history, and creates confusion about which copy is canonical. Worktrees provide real branch isolation with minimal overhead.

**Alternatives considered:** Directory copying (cp -r), temporary git clones.

## ADR-002: Background Processes Over Agent Teams

**Decision:** Use background `claude -p` processes, not Claude Code Agent Teams.

Agent Teams are session-scoped and don't persist across Claude Code sessions. Elmer explorations should outlive any single session — start explorations, close your terminal, review tomorrow. Background `claude -p` processes provide this persistence.

**Alternatives considered:** Agent Teams (session-scoped, don't persist), Claude Code plugin hooks (wrong lifecycle).

## ADR-003: SQLite Over JSON State Files

**Decision:** Use SQLite with WAL mode for state, not JSON files.

Concurrent explorations writing to a single JSON file risk corruption. SQLite handles concurrent access correctly via WAL mode. It also supports queries (find all explorations by status) without loading everything into memory.

**Alternatives considered:** Single JSON file, one JSON file per exploration.

## ADR-004: Click Over Argparse

**Decision:** Use Click for CLI, not argparse.

Click produces cleaner subcommand handling, better help text, and composable decorators. The single dependency is worth the ergonomic improvement for a CLI tool.

**Alternatives considered:** argparse (stdlib, no dependency but verbose), Typer (heavier, type-annotation magic).

## ADR-005: Static Templates Before Generated Prompts

**Decision:** Use static archetype templates with `$TOPIC` substitution in Phase 1. Defer two-stage prompt generation to Phase 2.

Static templates are debuggable, predictable, and sufficient for initial use. Two-stage generation (AI generates the prompt, then AI executes it) is the architectural goal but adds complexity that isn't justified until the core loop proves useful.

**Alternatives considered:** Jinja templating (overkill), AI-generated prompts from day one (premature complexity).

## ADR-006: Daemon Deferred to Phase 3

**Decision:** The daemon was deferred from Phase 1, implemented in Phase 3 after the manual loop and intelligence features proved useful. The daemon is a composition layer (ADR-010) that calls existing functions in a loop — no new execution model.

The phased approach validated the core principle: "Demonstrate value before adding complexity." Phase 1 proved the manual loop. Phase 2 added intelligence (topic generation, auto-approve). Phase 3 composed them into the daemon. Each phase justified the next.

**Alternatives considered:** Ship daemon immediately (risk: overbuilt before proving value).

*Revised: 2026-02-23, updated to reflect implemented state (ADR-023)*

## ADR-007: Synchronous `claude -p` for Meta-Operations

**Decision:** Use synchronous `subprocess.run` (via `worker.run_claude()`) for topic generation and auto-approve review, not background `subprocess.Popen`.

Explorations are long-running and benefit from backgrounding (ADR-002). Meta-operations — generating topics, reviewing proposals — are short-lived (3-5 turns) and their output is needed immediately by the caller. Topic generation must parse the output to spawn explorations. Auto-approve must parse the verdict to decide whether to merge. Both require the result synchronously.

This creates two invocation patterns: `spawn_claude()` for background exploration workers, `run_claude()` for synchronous meta-operations. The distinction maps cleanly to the use case.

**Alternatives considered:** Background all claude invocations and poll for completion (adds complexity for short operations), use a queue/callback pattern (overkill for sequential meta-operations).

## ADR-008: JSON Output Format for Cost Extraction

**Decision:** Use `--output-format json` for all `claude -p` invocations to extract token usage and cost data.

Synchronous meta-operations (`run_claude`) parse JSON from captured stdout. Background exploration workers (`spawn_claude`) write JSON to log files, parsed after completion by `parse_log_costs()`. Cost data is stored in SQLite — per-exploration columns on the `explorations` table, and a separate `costs` table for meta-operation costs.

JSON parsing is best-effort: if it fails (corrupted output, old CLI version), cost fields are left NULL. Cost tracking is informational and never blocks exploration flow.

Budget enforcement uses `--max-budget-usd`, delegating to the claude CLI for real-time budget caps.

**Alternatives considered:** Parsing text logs with regex (fragile, format not guaranteed), estimating from model + max_turns (inaccurate), separate `claude` invocation to query session costs (extra API call, may not exist).

## ADR-009: AI Archetype Selection as a Meta-Operation

**Decision:** Implement AI archetype selection as a synchronous meta-operation (like topic generation and auto-approve), using a dedicated `select-archetype.md` meta-prompt template.

The `--auto-archetype` flag triggers a synchronous `claude -p` call that reads the project docs and available archetypes, then returns a single archetype name. This runs before the exploration starts, so even pending (dependency-blocked) explorations store the AI-selected archetype.

The `-a` flag always overrides auto-selection, preserving full user control. This follows the principle: "AI suggests, user can always override." Auto-selection is opt-in (flag-based), not the default, consistent with the conservative autonomy principle (like `--auto-approve`).

Cost is tracked as an `archetype_select` meta-operation in the `costs` table, consistent with how `prompt_gen`, `generate`, and `auto_approve` costs are tracked.

**Alternatives considered:** Heuristic matching by keyword (fragile, doesn't understand project context), always using two-stage prompt generation to implicitly select behavior (conflates two concerns — archetype choice and prompt generation are separate decisions that compose).

## ADR-010: Daemon as Composition Layer

**Decision:** The daemon calls existing functions in a loop rather than introducing a new execution model. No new worker types, no new state transitions, no async framework.

The daemon cycle is: `_refresh_running()` (harvest) → `autoapprove.evaluate()` (gate) → `schedule_ready()` (schedule) → `generate_topics()` (replenish). Each of these already exists and works independently. The daemon is purely a composition layer with signal handling and PID management on top.

This means every daemon feature can also be triggered manually via existing CLI commands. The daemon automates the human cycle of `elmer status` → `elmer approve` → `elmer generate`, nothing more.

**Alternatives considered:** Event-driven architecture with callbacks (adds complexity, hides control flow), separate daemon process with IPC (overkill for a SQLite-coordinated system), async event loop (violates no-async constraint from ADR-002).

## ADR-011: PID File for Daemon Coordination

**Decision:** Use `.elmer/daemon.pid` to enforce single-instance daemon per project and enable `elmer daemon status`/`stop` commands.

The PID file is checked on daemon start (reject if another daemon is running), removed on graceful shutdown (SIGINT/SIGTERM), and validated on read (stale PID files from crashed daemons are detected via `os.kill(pid, 0)`).

This reuses the exact process-checking pattern from `worker.is_running()` (ADR-002), maintaining consistency across the codebase.

**Alternatives considered:** Lock files with `fcntl.flock` (more portable for NFS but Elmer is local-only), systemd socket activation (too platform-specific), no coordination (risk of multiple daemons clobbering state).

## ADR-012: Chain Actions as Shell Commands

**Decision:** `--on-approve` and `--on-reject` execute user-specified shell commands with `$ID` and `$TOPIC` variable substitution.

This provides maximum composability — chain actions can call `elmer generate`, `elmer explore`, or any other tool. The user is responsible for the commands they configure. Chain actions run synchronously with a 5-minute timeout and are best-effort (failures are logged, not fatal).

Chain actions are user-specified only. They are never auto-generated by AI to prevent unbounded autonomous command execution.

**Alternatives considered:** A DSL for chain logic (unnecessary complexity for v1), Python callbacks (not CLI-composable, requires code changes), automatic follow-up generation without explicit chaining (implemented separately via `--auto-followup`, serves a different use case).

## ADR-013: Global Insights Database at ~/.elmer/

**Decision:** Store cross-project insights in `~/.elmer/insights.db` (SQLite), separate from per-project `state.db`.

Insights are generalizable findings extracted from approved proposals — patterns, principles, anti-patterns that apply across projects. They live in the user's home directory because they span projects. Extraction happens post-approval via a synchronous `claude -p` meta-operation using `extract-insights.md`. Injection into new exploration prompts uses simple keyword matching (not semantic search) because it's good enough and requires no external dependencies.

Both extraction and injection are best-effort: failures never block the exploration or approval flow. Extraction is opt-in (`[insights] enabled = true`), injection is opt-out (`[insights] inject = true` by default when enabled).

**Alternatives considered:** Storing insights in per-project `state.db` (defeats cross-project purpose), vector database for semantic search (adds external dependency, overkill for v1), embedding-based similarity (same dependency concern), no automatic extraction — manual only (loses the value of autonomous insight accumulation).

## ADR-014: Question Mining as Meta-Operation

**Decision:** `elmer mine-questions` runs a synchronous `claude -p` meta-operation (consistent with ADR-007) using a `mine-questions.md` archetype that reads project docs and outputs clustered questions.

Question mining produces `CLUSTER: <name>` / `- <question>` formatted output, parsed into `dict[str, list[str]]`. With `--spawn`, questions are converted to exploration topics and spawned as explorations. This reuses the existing `start_exploration()` flow — no new execution model.

The `--cluster` filter allows targeting specific question themes without re-running the AI. `--max-per-cluster` caps how many questions per cluster become explorations, preventing topic explosion.

**Alternatives considered:** Regex-based question extraction from docs (misses implicit gaps, which are the most valuable), always spawning explorations (expensive, many questions don't warrant full exploration), storing mined questions in SQLite (adds schema complexity for a stateless operation — mine fresh each time).

## ADR-015: Five-Document Scaffolding as Templates

**Decision:** `elmer init --docs` generates five project documents (CLAUDE.md, DESIGN.md, DECISIONS.md, ROADMAP.md, CONTEXT.md) from built-in Python string templates in `scaffold.py`, not from archetype markdown files.

Scaffolding is a one-time project setup operation, not an exploration meta-prompt. Templates use `{project_name}` Python format strings (not `$TOPIC` substitution) because they need project-specific data. Files are only created if they don't already exist — safe to run repeatedly.

The five-document pattern is the same one that makes Elmer's own project effective with Claude Code: orientation, architecture, decisions, roadmap, and context. Scaffolding it for other projects codifies institutional knowledge about effective AI-assisted development.

**Alternatives considered:** Using archetype-style `$TOPIC` templates (wrong abstraction — scaffolding isn't exploration), Cookiecutter/copier (external dependency for a simple operation), AI-generated docs via `claude -p` (expensive and unpredictable for what should be deterministic scaffolding).

## ADR-016: Archetype Stats from Existing Exploration Data

**Decision:** `elmer archetypes stats` computes archetype effectiveness metrics (approval rate, average cost, follow-up count) by querying the existing `explorations` table. No new tables, no new columns, no tracking changes.

All the data needed for archetype analytics already exists in the explorations table: `archetype`, `status`, `cost_usd`. The approval rate (approved / (approved + rejected)) is the primary signal. Stats are computed on-demand, not cached, because the exploration table is small enough that aggregation is instant.

**Alternatives considered:** A dedicated `archetype_stats` table updated on each status change (premature optimization — the explorations table is sufficient), per-archetype scoring models (insufficient data in early use to justify complexity), human feedback collection (valuable but adds UI complexity — deferred).

## ADR-017: Heuristic Attention Routing

**Decision:** `elmer review --prioritize` ranks proposals using a deterministic heuristic scoring function, not AI evaluation. Scoring factors: dependents blocked (+30 per blocker), staleness (+1 per hour, max 24), diff size (small = +10), failed status (+5).

The factors reflect what makes a proposal worth reviewing first: blocking other work is highest priority, then age (prevent queue rot), then ease of review (small diffs), then attention-needing status (failed). The heuristic is fast, free (no API call), and transparent — scores and reasons are displayed.

AI-based impact assessment was considered but rejected for v1: it would cost money on every `elmer review --prioritize` call, and the heuristic captures the most important signals (blockers, staleness) without AI.

**Alternatives considered:** AI evaluation via `claude -p` (expensive per invocation, overkill for queue ordering), user-configurable priority weights (premature — let the default heuristic prove useful first), no prioritization at all (fine for <10 proposals, but doesn't scale when daemon generates many).

## ADR-018: Invariant Enforcement as Meta-Operation

**Decision:** `elmer validate` and `elmer approve --validate-invariants` run a synchronous `claude -p` meta-operation (consistent with ADR-007) using a `validate-invariants.md` archetype that checks and auto-fixes document consistency.

Default invariant rules check document consistency: ADR count alignment between CLAUDE.md and DECISIONS.md, phase status consistency across ROADMAP.md and CLAUDE.md, feature-code correspondence. Custom rules can be configured in `[invariants] rules` in `config.toml`.

The AI both checks and fixes — if an invariant fails, it edits the file to restore consistency. This is appropriate because the invariants are about document metadata (counts, status labels), not substantive content. The fix is always a small, mechanical edit.

**Alternatives considered:** Pure regex/programmatic checks (would work for ADR counting but not for semantic checks like "does phase status match?"), separate check and fix steps (adds friction — if you know the fix is mechanical, just do it), running invariant checks on every status change (too expensive — only needed after merge changes project state).

## ADR-019: Global Project Registry for Multi-Project Dashboard

**Decision:** Store a list of known Elmer project paths in `~/.elmer/projects.json`. Updated automatically when `elmer init` runs or any command touches `.elmer/`. `elmer status --all-projects` reads this registry and queries each project's `state.db` for aggregated status.

The registry is a simple JSON array of absolute paths. Stale entries (projects where `.elmer/` no longer exists) are pruned automatically on read. This reuses the `~/.elmer/` global directory established by ADR-013 (insights database).

The dashboard aggregates counts by status (running, done, pending, approved, rejected, failed) and total cost per project. When multiple projects are registered, a totals row is shown. This addresses the Phase Gate requirement: "attention routing helps a user managing 10+ pending proposals across 2+ projects."

**Alternatives considered:** Scanning filesystem for `.elmer/` directories (slow, unpredictable depth), per-project config pointing to other projects (fragile cross-references), SQLite table in `~/.elmer/insights.db` (mixing concerns — project registry isn't an insight).

## ADR-020: PR Creation via gh CLI

**Decision:** `elmer pr ID` pushes the exploration branch to the remote and creates a GitHub PR using the `gh` CLI. PROPOSAL.md content becomes the PR body. This is a separate command (not a flag on `explore`) because PR creation is a review-time decision, not an exploration-time decision.

The `gh` CLI is an optional dependency — `elmer pr` fails with a clear error if `gh` is not installed. This avoids adding `PyGithub` or `requests` as dependencies and leverages the user's existing GitHub authentication via `gh auth`.

The PR title is `elmer: {topic}` (truncated to 70 chars). The PR body is the full PROPOSAL.md content plus an Elmer attribution footer. The exploration must be in `done`, `failed`, or `running` status — you can create a PR at any point after the branch exists.

**Alternatives considered:** `--pr` flag on `explore` (conflates exploration with review workflow — user may not want a PR for every exploration), PyGithub library (adds dependency, requires separate auth config), automatic PR on exploration completion (too aggressive — user should decide which explorations deserve PRs).

## ADR-021: Topic List Files with Batch Command

**Decision:** `elmer batch <file>` reads a `---`-separated markdown file, infers the archetype from the filename stem, and spawns one exploration per topic section. `--chain` creates a dependency chain so topics execute and merge sequentially.

Topic list files live at `.elmer/<archetype>.md` (e.g., `.elmer/explore-act.md`). This is a convention, not a requirement — any path works, but the filename-to-archetype inference makes the convention self-documenting. Files at `.elmer/` root don't collide with archetype templates (which live in `.elmer/archetypes/`).

The `---` separator was chosen because it's a standard markdown thematic break, visually unambiguous, and trivially parseable with `text.split('---')`. Each section between separators is one topic. Multi-line sections are preserved as-is — the full text becomes the `$TOPIC` substitution value. The first section is discarded if it starts with `#` (header/comments).

The `--chain` flag uses the existing `--depends-on` mechanism (ADR dependencies table, `schedule_ready()`). Topic 2 depends on topic 1, topic 3 depends on topic 2, etc. This ensures each exploration starts after the previous is approved and merged, working on the latest code — which eliminates merge conflicts when multiple proposals touch overlapping files.

Existing `elmer explore -f topics.txt` is preserved for backwards compatibility. The key differences: `-f` is line-based and parallel; `batch` is `---`-separated, supports multi-line topics, infers archetype from filename, and supports `--chain`.

**Alternatives considered:** Enhancing `-f` to support the new format (would break existing users or require format detection), YAML/TOML topic files (heavier syntax for what's essentially a list of text blocks), per-topic frontmatter for overrides (deferred — global CLI flags cover the common case).

## ADR-022: Claude Code Skill Scaffolding as Elmer Feature

**Decision:** `elmer init --skills` generates project-specific Claude Code skills in `.claude/skills/` by reading existing project documentation and detecting which review lenses apply.

Elmer archetypes and Claude Code skills are parallel systems with overlapping analysis methodology but different runtimes. Archetypes run in background `claude -p` sessions, output PROPOSAL.md to git branches, and are tracked in SQLite. Skills run interactively in Claude Code sessions, output action lists in chat, and have no persistent state. Both are useful. Neither replaces the other.

The overlap (e.g., `coherence-audit.md` archetype ≈ `/coherence` skill) is tolerated rather than unified through a shared template layer. A shared template directory was considered but adds indirection without reducing drift enough to justify the infrastructure. If the analysis methodology in an archetype and its corresponding skill diverge, they diverge — they serve different moments (autonomous batch research vs. interactive design thinking).

Project-specific skills are different: they encode domain knowledge (mission principles, cultural constraints, UX personas) that's specific to the project and benefits from being generated from existing docs rather than hand-crafted. `elmer init --skills` reads CLAUDE.md, DESIGN.md, and CONTEXT.md, detects signals (mission principles, i18n references, compliance requirements), and generates `.claude/skills/<name>/SKILL.md` files with project-specific content filled in. Only creates skills that don't exist — safe to run repeatedly.

This positions Elmer as infrastructure that makes both autonomous exploration (via archetypes) and interactive analysis (via generated skills) more effective for any project.

**Alternatives considered:** Shared template library at `~/.config/analysis-lenses/` with both systems reading from one source (adds a third location to maintain, indirection cost exceeds drift cost), `elmer sync-skills` command to regenerate skills on demand (implies ongoing sync obligation — generation at init time is sufficient), Claude Code plugin (couples Elmer to Claude Code's evolving plugin API, constrains Elmer's process model).

## ADR-023: Mutable ADRs with Git Audit Trail

**Decision:** ADRs are mutable living documents. Update them directly — add, revise, or replace content in place. Do not create superseding ADRs or use withdrawal ceremony. When substantially revising an ADR, add `*Revised: [date], [reason]*` at the section's end. Git history serves as the full audit trail.

The previous approach (append-only, new ADR to supersede old) adds ceremony without value at Elmer's scale (22 ADRs). It creates supersession chains that are harder to follow than simply reading the current state of each ADR. Git provides a complete, queryable audit trail via `git log -p DECISIONS.md` — maintaining a parallel audit trail in the document itself is redundant.

This aligns with how DESIGN.md is already treated (mutable, update to reflect actual decisions) and eliminates the philosophical inconsistency between the two documents.

Adopted from the SRF Yogananda Teachings project's ADR governance model.

**Alternatives considered:** Keep append-only (status quo — adds overhead, creates supersession chains), hybrid approach where only "major" reversals get new ADRs (subjective threshold, worst of both worlds).

## ADR-024: MCP Server for Structured Tool Access

**Decision:** Expose Elmer state and operations as MCP tools via a stdio JSON-RPC server (`elmer mcp`), using Anthropic's `mcp` Python SDK (FastMCP).

Elmer's CLI returns formatted text tables that Claude Code must parse as unstructured text — lossy, brittle, and prone to misinterpretation. The MCP server wraps the same module functions (`state.py`, `costs.py`, `insights.py`, `config.py`, `explore.py`, `gate.py`) and returns structured JSON that Claude Code reasons about natively.

10 tools total: 6 read-only (status, review, costs, tree, archetypes, insights) + 4 mutation (explore, approve, reject, cancel). Mutation tools catch `SystemExit` from gate functions (which use `sys.exit(1)` for validation) and convert to structured error responses — the server never crashes.

The server is a presentation layer. Each tool opens a DB connection, queries, closes, and returns JSON — the same per-call pattern as CLI commands. No connection pooling, no persistent state between tool calls.

**Alternatives considered:** REST API (adds web framework dependency, requires port management, conflicts with no-web-framework constraint), enhancing CLI with `--json` output flags (per-command work, doesn't provide tool discovery or schema introspection that MCP gives for free).

*Revised: 2026-02-23, added Phase 2 mutation tools*

## ADR-025: Event-Driven Document Maintenance in Scaffolding

**Decision:** Upgrade `elmer init --docs` scaffolding to include event-driven document maintenance tables, canonical homes, per-session checklists, documentation rules, and a documentation–code transition lifecycle. Apply the same event-driven format to Elmer's own CLAUDE.md.

The previous scaffold template used a simple "File / Type / Update when..." table that listed each file with generic triggers ("Architecture changes"). This format requires judgment about what constitutes an architecture change and doesn't specify cascade effects (e.g., adding an ADR requires updating both DECISIONS.md and the ADR count in CLAUDE.md).

The event-driven format maps specific events to specific document updates: "When this happens → update these documents." This is more actionable, more machine-followable, and teaches the maintenance discipline that prevents drift across AI sessions.

The enhanced scaffold also includes:
- **Canonical homes** — each piece of information lives in one place, other files reference. Prevents duplication drift.
- **Per-session checklist** — mechanical checks to run after each session (ADR count alignment, last-updated footers).
- **Documentation rules** — mutable ADRs, section-level change tracking, no cross-document duplication.
- **Documentation–code transition** — 4-stage lifecycle (spec → implemented → diverged → living reference) with status markers and section-level tracking.

These patterns were proven in a mature project (SRF Yogananda Teachings, 123 ADRs) and back-ported to Elmer's scaffolding. The scaffold teaches the full pattern from day one rather than requiring projects to discover it organically.

**Alternatives considered:** Keeping the simple table and letting projects evolve their own maintenance patterns (loses the accumulated knowledge), making the scaffold AI-generated per-project via `claude -p` (expensive and unpredictable for what should be deterministic templates, consistent with ADR-015), adding maintenance rules as a separate post-init step (fragments the setup experience).
