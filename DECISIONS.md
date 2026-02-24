# Elmer — Decisions

Architecture Decision Records. Mutable living documents — update directly when decisions evolve. When substantially revising an ADR, add `*Revised: [date], [reason]*` at the section's end. Git history serves as the full audit trail.

13 ADRs recorded.

## Domain Index

| ADR | Domain | Summary |
|-----|--------|---------|
| ADR-001 | Git | Worktrees over directory copying |
| ADR-002 | Process | Background `claude -p` over Agent Teams |
| ADR-003 | Storage | SQLite over JSON state files |
| ADR-007 | Process | Synchronous `claude -p` for meta-operations |
| ADR-008 | Process | JSON output format for cost extraction |
| ADR-010 | Architecture | Daemon as composition layer |
| ADR-012 | Autonomy | Chain actions as shell commands |
| ADR-013 | Storage | Global insights database at ~/.elmer/ |
| ADR-015 | Scaffolding | Five-document scaffolding as templates |
| ADR-022 | Integration | Claude Code skill scaffolding as Elmer feature |
| ADR-024 | Integration | MCP server for structured tool access |
| ADR-026 | Process | Exploration archetypes as Claude Code custom subagents |
| ADR-027 | Terminology | Rename "reject/rejected" to "decline/declined" |

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

## ADR-010: Daemon as Composition Layer

**Decision:** The daemon calls existing functions in a loop rather than introducing a new execution model. No new worker types, no new state transitions, no async framework.

The daemon cycle is: `_refresh_running()` (harvest) → `autoapprove.evaluate()` (gate) → `schedule_ready()` (schedule) → `generate_topics()` (replenish). Each of these already exists and works independently. The daemon is purely a composition layer with signal handling and PID management on top.

This means every daemon feature can also be triggered manually via existing CLI commands. The daemon automates the human cycle of `elmer status` → `elmer approve` → `elmer generate`, nothing more.

**Alternatives considered:** Event-driven architecture with callbacks (adds complexity, hides control flow), separate daemon process with IPC (overkill for a SQLite-coordinated system), async event loop (violates no-async constraint from ADR-002).

## ADR-012: Chain Actions as Shell Commands

**Decision:** `--on-approve` and `--on-decline` execute user-specified shell commands with `$ID` and `$TOPIC` variable substitution.

This provides maximum composability — chain actions can call `elmer generate`, `elmer explore`, or any other tool. The user is responsible for the commands they configure. Chain actions run synchronously with a 5-minute timeout and are best-effort (failures are logged, not fatal).

Chain actions are user-specified only. They are never auto-generated by AI to prevent unbounded autonomous command execution.

**Alternatives considered:** A DSL for chain logic (unnecessary complexity for v1), Python callbacks (not CLI-composable, requires code changes), automatic follow-up generation without explicit chaining (implemented separately via `--auto-followup`, serves a different use case).

## ADR-013: Global Insights Database at ~/.elmer/

**Decision:** Store cross-project insights in `~/.elmer/insights.db` (SQLite), separate from per-project `state.db`.

Insights are generalizable findings extracted from approved proposals — patterns, principles, anti-patterns that apply across projects. They live in the user's home directory because they span projects. Extraction happens post-approval via a synchronous `claude -p` meta-operation using `extract-insights.md`. Injection into new exploration prompts uses simple keyword matching (not semantic search) because it's good enough and requires no external dependencies.

Both extraction and injection are best-effort: failures never block the exploration or approval flow. Extraction is opt-in (`[insights] enabled = true`), injection is opt-out (`[insights] inject = true` by default when enabled).

**Alternatives considered:** Storing insights in per-project `state.db` (defeats cross-project purpose), vector database for semantic search (adds external dependency, overkill for v1), embedding-based similarity (same dependency concern), no automatic extraction — manual only (loses the value of autonomous insight accumulation).

## ADR-015: Five-Document Scaffolding as Templates

**Decision:** `elmer init --docs` generates five project documents (CLAUDE.md, DESIGN.md, DECISIONS.md, ROADMAP.md, CONTEXT.md) from built-in Python string templates in `scaffold.py`, not from archetype markdown files.

Scaffolding is a one-time project setup operation, not an exploration meta-prompt. Templates use `{project_name}` Python format strings (not `$TOPIC` substitution) because they need project-specific data. Files are only created if they don't already exist — safe to run repeatedly.

The five-document pattern is the same one that makes Elmer's own project effective with Claude Code: orientation, architecture, decisions, roadmap, and context. Scaffolding it for other projects codifies institutional knowledge about effective AI-assisted development.

**Alternatives considered:** Using archetype-style `$TOPIC` templates (wrong abstraction — scaffolding isn't exploration), Cookiecutter/copier (external dependency for a simple operation), AI-generated docs via `claude -p` (expensive and unpredictable for what should be deterministic scaffolding).

## ADR-022: Claude Code Skill Scaffolding as Elmer Feature

**Decision:** `elmer init --skills` generates project-specific Claude Code skills in `.claude/skills/` by reading existing project documentation and detecting which review lenses apply.

Elmer archetypes and Claude Code skills are parallel systems with overlapping analysis methodology but different runtimes. Archetypes run in background `claude -p` sessions, output PROPOSAL.md to git branches, and are tracked in SQLite. Skills run interactively in Claude Code sessions, output action lists in chat, and have no persistent state. Both are useful. Neither replaces the other.

The overlap (e.g., `coherence-audit.md` archetype ≈ `/coherence` skill) is tolerated rather than unified through a shared template layer. A shared template directory was considered but adds indirection without reducing drift enough to justify the infrastructure. If the analysis methodology in an archetype and its corresponding skill diverge, they diverge — they serve different moments (autonomous batch research vs. interactive design thinking).

Project-specific skills are different: they encode domain knowledge (mission principles, cultural constraints, UX personas) that's specific to the project and benefits from being generated from existing docs rather than hand-crafted. `elmer init --skills` reads CLAUDE.md, DESIGN.md, and CONTEXT.md, detects signals (mission principles, i18n references, compliance requirements), and generates `.claude/skills/<name>/SKILL.md` files with project-specific content filled in. Only creates skills that don't exist — safe to run repeatedly.

This positions Elmer as infrastructure that makes both autonomous exploration (via archetypes) and interactive analysis (via generated skills) more effective for any project.

**Alternatives considered:** Shared template library at `~/.config/analysis-lenses/` with both systems reading from one source (adds a third location to maintain, indirection cost exceeds drift cost), `elmer sync-skills` command to regenerate skills on demand (implies ongoing sync obligation — generation at init time is sufficient), Claude Code plugin (couples Elmer to Claude Code's evolving plugin API, constrains Elmer's process model).

## ADR-024: MCP Server for Structured Tool Access

**Decision:** Expose Elmer state and operations as MCP tools via a stdio JSON-RPC server (`elmer mcp`), using Anthropic's `mcp` Python SDK (FastMCP).

Elmer's CLI returns formatted text tables that Claude Code must parse as unstructured text — lossy, brittle, and prone to misinterpretation. The MCP server wraps the same module functions (`state.py`, `costs.py`, `insights.py`, `config.py`, `explore.py`, `gate.py`) and returns structured JSON that Claude Code reasons about natively.

17 tools total: 6 read-only (status, review, costs, tree, archetypes, insights) + 7 mutation (explore, approve, decline, cancel, retry, clean, pr) + 3 intelligence (generate, validate, mine-questions) + 1 batch. Mutation tools catch `SystemExit` from gate functions (which use `sys.exit(1)` for validation) and convert to structured error responses — the server never crashes.

The server is a presentation layer. Each tool opens a DB connection, queries, closes, and returns JSON — the same per-call pattern as CLI commands. No connection pooling, no persistent state between tool calls.

**Alternatives considered:** REST API (adds web framework dependency, requires port management, conflicts with no-web-framework constraint), enhancing CLI with `--json` output flags (per-command work, doesn't provide tool discovery or schema introspection that MCP gives for free).

*Revised: 2026-02-23, expanded to 17 tools, reject→decline rename (ADR-027)*

## ADR-026: Exploration Archetypes as Claude Code Custom Subagents

**Decision:** Convert all exploration archetypes and meta-operation templates into Claude Code custom subagent definitions, invoked via `--agents`/`--agent` CLI flags on `claude -p`.

Previously, archetypes were prompt templates with `$TOPIC` substitution — the entire archetype was injected into the `-p` prompt. This works but wastes prompt tokens on methodology instructions every invocation and prevents Claude Code from applying tool restrictions or model overrides per archetype.

Claude Code custom subagents (`.claude/agents/` markdown files with YAML frontmatter) provide:
- **System prompt separation** — the archetype methodology becomes the agent's system prompt; the `-p` prompt carries only the topic. This is structurally correct: methodology is context, topic is the task.
- **Tool restrictions** — audit archetypes get read-only tools (`Read, Grep, Glob, Bash`), exploration archetypes get full tools including `Edit, Write`. Enforced by Claude Code, not by prompt instructions.
- **Model selection** — meta-operation agents specify `model: sonnet` in frontmatter, avoiding the overhead of opus for lightweight tasks like review-gate or topic generation.
- **Project-local overrides** — `elmer init --agents` scaffolds to `.claude/agents/`, where users can customize agent behavior without modifying bundled defaults.

**Architecture:**

23 bundled agent definitions in `src/elmer/agents/`:
- 8 exploration agents (explore-act, explore, prototype, adr-proposal, benchmark, dead-end-analysis, devil-advocate, question-cluster)
- 8 audit agents (consistency-audit, coherence-audit, architecture-audit, documentation-audit, mission-audit, operational-audit, opportunity-scan, workflow-audit)
- 7 meta-operation agents (review-gate, generate-topics, select-archetype, extract-insights, mine-questions, validate-invariants, prompt-gen)

**Resolution order:** project-local `.claude/agents/elmer-<name>.md` → bundled `src/elmer/agents/<name>.md`. Meta agents use `elmer-meta-<name>` prefix.

**Invocation:** `worker.py` builds `--agents '{name: {description, prompt, tools, model}}'` inline JSON + `--agent name` flags. The inline JSON approach avoids filesystem dependency — agents work correctly when `claude -p` runs in worktree directories where `.claude/agents/` doesn't exist.

**Backwards compatibility:** When no agent definition exists for an archetype, the system falls back to the existing `$TOPIC` template substitution. All existing archetypes continue to work.

**Alternatives considered:** Filesystem-based agents only (breaks in worktrees where `.claude/agents/` isn't visible), Agent Teams for parallel explorations (session-scoped, don't persist — consistent with ADR-002), prompt-only approach with tool restrictions in prompt text (unenforceable, wastes tokens), separate agent runner binary (unnecessary complexity when `claude -p` already supports `--agents`).

## ADR-027: Rename "Reject/Rejected" to "Decline/Declined"

**Decision:** Rename all user-facing occurrences of "reject"/"rejected" to "decline"/"declined" across CLI commands, MCP tools, status values, database columns, function names, and documentation.

"Reject" carries a harsh, judgmental connotation that doesn't match the actual operation: the user is simply choosing not to merge a proposal. "Decline" is softer and more accurate — it conveys "not this time" rather than "this is bad." Since Elmer is designed for autonomous research where many proposals are expected to be discarded (broad surveys, dead-end analysis), the terminal state label should feel routine, not punitive.

**Scope of change:**

- CLI: `elmer reject` → `elmer decline`, `--on-reject` → `--on-decline`
- MCP: `elmer_reject` → `elmer_decline`
- State: status value `"rejected"` → `"declined"` in SQLite
- Database: column `on_reject` → `on_decline` (with migration)
- Functions: `reject_exploration()` → `decline_exploration()`
- All documentation updated

**Intentionally unchanged:** The AI review gate protocol keyword `VERDICT: REJECT` in `autoapprove.py` and the `review-gate` meta-agent. These are instructions to the AI model, not user-facing terminology. The AI protocol uses a binary APPROVE/REJECT vocabulary that the model recognizes reliably — renaming it risks parsing failures without user benefit.

**Migration:** SQLite schema migration renames the `on_reject` column to `on_decline` and updates all status values from `"rejected"` to `"declined"`. Both operations are idempotent (wrapped in try/except for re-run safety).

**Alternatives considered:** Keeping "reject" (functional but tonally misaligned with the tool's philosophy), "skip" (implies the proposal might be revisited), "discard" (accurate but already used for the git operation description), "pass" (ambiguous — could mean "approve without review").
