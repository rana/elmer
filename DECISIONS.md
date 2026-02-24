# Elmer — Decisions

Architecture Decision Records. Mutable living documents — update directly when decisions evolve. When substantially revising an ADR, add `*Revised: [date], [reason]*` at the section's end. Git history serves as the full audit trail.

15 ADRs recorded.

## Domain Index

| ADR | Domain | Summary |
|-----|--------|---------|
| ADR-001 | Git | Worktrees over directory copying |
| ADR-002 | Process | Claude invocation patterns |
| ADR-003 | Storage | SQLite over JSON state files |
| ADR-010 | Process | Daemon as composition layer |
| ADR-012 | Process | Chain actions as shell commands |
| ADR-013 | Storage | Global insights database at ~/.elmer/ |
| ADR-015 | Scaffolding | Five-document scaffolding as templates |
| ADR-022 | Scaffolding | Claude Code skill scaffolding as Elmer feature |
| ADR-024 | Integration | MCP server for structured tool access |
| ADR-026 | Process | Exploration archetypes as Claude Code custom subagents |
| ADR-028 | Process | Proposal amendment workflow |
| ADR-029 | Git | PROPOSAL.md merge hygiene and approve_all resilience |
| ADR-030 | Intelligence | Convergence digests and decline reasons |
| ADR-031 | Process | Ensemble exploration and synthesis |
| ADR-032 | Storage | Archive as source of truth for completed explorations |

---

## ADR-001: Git Worktrees Over Directory Copying

**Decision:** Use git worktrees for branch isolation, not directory copying.

Worktrees share `.git`, are instant to create, and space-efficient. Directory copying wastes disk, duplicates git history, and creates confusion about which copy is canonical. Worktrees provide real branch isolation with minimal overhead.

**Alternatives considered:** Directory copying (cp -r), temporary git clones.

## ADR-002: Claude Invocation Patterns

**Decision:** Two invocation patterns for `claude -p`, both using `--output-format json`:

- **Background** (`spawn_claude`): Explorations. Long-running, PID-tracked, output to log files. Agent Teams were rejected — they're session-scoped and don't persist. Elmer explorations should outlive any single session.
- **Synchronous** (`run_claude`): Meta-operations (topic generation, auto-approve review, prompt generation, archetype selection, insight extraction, question mining, invariant validation). Short-lived (3-5 turns), output parsed immediately by the caller.

**Cost extraction:** All invocations use `--output-format json`. Synchronous operations parse JSON from captured stdout. Background workers write JSON to log files, parsed after completion by `parse_log_costs()`. Cost data is stored in SQLite. JSON parsing is best-effort: if it fails, cost fields are left NULL. Cost tracking never blocks exploration flow. Budget enforcement uses `--max-budget-usd`, delegating to the claude CLI for real-time caps.

**Alternatives considered:** Agent Teams (session-scoped, don't persist), Claude Code plugin hooks (wrong lifecycle), background all invocations and poll (adds complexity for short operations), queue/callback pattern (overkill for sequential meta-operations), parsing text logs with regex (fragile), estimating costs from model + max_turns (inaccurate).

*Revised: 2026-02-23, consolidated from ADR-002 (background processes), ADR-007 (synchronous meta-ops), ADR-008 (JSON output/cost extraction)*

## ADR-003: SQLite Over JSON State Files

**Decision:** Use SQLite with WAL mode for state, not JSON files.

Concurrent explorations writing to a single JSON file risk corruption. SQLite handles concurrent access correctly via WAL mode. It also supports queries (find all explorations by status) without loading everything into memory.

**Alternatives considered:** Single JSON file, one JSON file per exploration.

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

*Revised: 2026-02-23, expanded to 17 tools*

## ADR-026: Exploration Archetypes as Claude Code Custom Subagents

**Decision:** Convert all exploration archetypes and meta-operation templates into Claude Code custom subagent definitions, invoked via `--agents`/`--agent` CLI flags on `claude -p`.

Previously, archetypes were prompt templates with `$TOPIC` substitution — the entire archetype was injected into the `-p` prompt. This works but wastes prompt tokens on methodology instructions every invocation and prevents Claude Code from applying tool restrictions or model overrides per archetype.

Claude Code custom subagents (`.claude/agents/` markdown files with YAML frontmatter) provide:
- **System prompt separation** — the archetype methodology becomes the agent's system prompt; the `-p` prompt carries only the topic. This is structurally correct: methodology is context, topic is the task.
- **Tool restrictions** — action archetypes (explore-act, prototype, adr-proposal, benchmark) get full tools including `Edit, Write`; analysis and audit archetypes get `Write` without `Edit`. Enforced by Claude Code, not by prompt instructions.
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

*ADR-027 (reject→decline rename) retired: completed migration, rationale preserved in git history. The AI review gate protocol retains REJECT (see DESIGN.md, Auto-Approve Gate section).*

## ADR-028: Proposal Amendment Workflow

**Decision:** Add `elmer amend ID "feedback"` as a first-class lifecycle operation.

Elmer's model was binary — approve (merge as-is) or decline (discard entirely). Real editorial workflows need a refinement loop. `elmer amend` spawns a Claude session in the existing worktree to revise PROPOSAL.md based on editorial direction. The dedicated `elmer-meta-amend` agent has `Read, Grep, Glob, Bash, Edit, Write` — it can both read and edit existing files, unlike analysis agents. State transition: `done → amending → done`. The exploration re-enters the review queue after amendment. Multiple amendment rounds are supported — amend is idempotent on the worktree.

The amend agent is editorial, not exploratory: it applies directed changes and re-evaluates coherence, but does not expand scope. This distinction prevents amendment from becoming a second exploration.

**Alternatives considered:** Manual proposal editing (works but misses cascading cross-reference cleanup), decline-and-re-explore with scoped topic (wastes good generated content), storing amendment history in SQLite (adds complexity — git history on the branch already tracks revisions).

## ADR-029: PROPOSAL.md Merge Hygiene and approve_all Resilience

**Decision:** Three changes to the merge contract:

1. **Post-merge PROPOSAL.md cleanup.** After `merge_branch()` succeeds, `approve_exploration()` removes PROPOSAL.md from the working tree and commits the deletion. PROPOSAL.md is an elmer artifact (archived to `.elmer/proposals/`), not a project deliverable. Leaving it in main causes `both added` merge conflicts on every subsequent approval. The cleanup commit message references the archive location.

2. **`approve_all` aborts failed merges.** When `approve_all()` catches a merge failure (SystemExit), it calls `git merge --abort` before continuing to the next exploration. Without this, the first failed merge leaves git in a dirty state, cascading all subsequent merge attempts — even conflict-free ones.

3. **Self-healing `.elmer/.gitignore`.** `_require_elmer()` (called by every command) now calls `ensure_gitignore()`, which writes the current gitignore entries. Projects initialized before the inner gitignore feature existed get it automatically on next command. `init_project()` also always writes (not guards with `if not exists`), ensuring entries stay current as new patterns are added (e.g., `daemon.pid`).

**Context:** Discovered via real-world `elmer approve --all` in a project with multiple explorations. First approval succeeded but left PROPOSAL.md in main. Second approval conflicted on `both added: PROPOSAL.md`. The `approve_all` loop continued without aborting, leaving git in a merge state that blocked all subsequent operations. The project also lacked `.elmer/.gitignore` because it was initialized before that feature existed.

**Alternatives considered:** Adding PROPOSAL.md to project `.gitignore` (imposes on user's project), instructing Claude not to commit PROPOSAL.md (unreliable — Claude has Bash/git access and may commit as part of explore-act workflow), squash-merge to avoid PROPOSAL.md entirely (loses branch history).

## ADR-030: Convergence Digests and Decline Reasons

**Decision:** Add two interconnected features that close the feedback loop in the daemon's autonomy cycle:

1. **Decline reasons.** `elmer decline ID "reason"` stores a `decline_reason` in SQLite and in the proposal archive metadata. Decline reasons are learning signals — they tell the system (and future explorations) what the human reviewer cares about, what framing was wrong, and what directions to avoid.

2. **Convergence digests.** `elmer digest` reads the proposal archive (approved proposals, declined proposals with reasons, exploration history) and synthesizes a convergence document via the `elmer-meta-digest` agent. The digest identifies themes where explorations agree, contradictions that need resolution, gaps no one has investigated, patterns in what gets declined, and 3-5 recommended next directions. Digests are stored in `.elmer/digests/` as timestamped markdown files.

3. **Digest-aware generation.** `generate_topics()` reads the latest digest and includes it in the prompt context, so topic proposals fill identified gaps instead of random-walking through the problem space.

4. **Daemon synthesis step.** The daemon loop gains a new step between scheduling and generation: when approvals since the last digest exceed a configurable threshold (`[digest] threshold = 5`), the daemon runs a synthesis before generating new topics. This creates a two-timescale system: fast loop (explore → approve) and slow loop (digest → generate → explore → digest).

**Architecture:**
- `digest.py`: Module for synthesis. Reads proposals from `.elmer/proposals/`, decline reasons from SQLite, prior digests from `.elmer/digests/`. Calls `run_claude()` with the `elmer-meta-digest` agent. Stores result with metadata header.
- `agents/digest.md`: Meta-agent definition. Read-only tools (`Read, Grep, Glob, Bash`), sonnet model. Prompt instructs synthesis across convergence, contradictions, gaps, decline patterns, and recommendations.
- `archetypes/digest.md`: Template fallback with `$HISTORY`, `$APPROVED_PROPOSALS`, `$DECLINED_PROPOSALS`, `$PREVIOUS_DIGEST` substitution.
- Daemon step 5 (between schedule and generate): conditional on `approvals_since_last_digest() >= threshold`. Best-effort: digest failure never blocks the cycle.
- Generate integration: `_read_latest_digest()` in `generate.py` reads the most recent digest file and injects it as a `## Recent Digest` prompt section. Best-effort: missing digest just means no injection.
- MCP tool: `elmer_digest` with optional `model`, `since`, `topic_filter` parameters.
- Config section: `[digest] model = "sonnet"`, `max_turns = 5`, `threshold = 5`.

**Why this matters:** Without convergence, the autonomy loop is a random walk. Each exploration starts fresh from static project docs. The daemon can generate and approve work, but it doesn't learn between cycles — it can't tell that three explorations converged on the same bottleneck, or that every declined proposal was too broad. The digest is the slow feedback loop that turns the daemon from "busy" into "directed."

**Alternatives considered:** Extending the insights system to handle synthesis (insights are per-proposal extractions, not cross-proposal synthesis — different operation), injecting all sibling proposal summaries into each new exploration (considered in CONTEXT.md and rejected: too noisy, dilutes topic focus, unbounded prompt growth), embedding-based semantic search across proposals (adds vector DB dependency), no explicit convergence — rely on the human to steer via topic generation (defeats the purpose of the autonomy loop).

## ADR-031: Ensemble Exploration and Synthesis

**Decision:** Add ensemble exploration — running N explorations of the same topic with independent Claude sessions, then synthesizing the proposals into a single consolidated result.

**Core principle:** LLM non-determinism is noise in single runs but signal in aggregate. When multiple independent explorations converge on the same conclusion, that's a stronger signal than any single run. When they diverge, the divergence reveals genuine ambiguity. Ensemble synthesis exploits this by design.

**Architecture:**

1. **Schema.** Two new columns on `explorations`: `ensemble_id TEXT` (groups replicas and synthesis) and `ensemble_role TEXT` (`'replica'` or `'synthesis'`). No new tables — ensemble status is derived from component explorations.

2. **CLI.** `elmer explore "topic" --replicas N` spawns N explorations with suffix slugs sharing an `ensemble_id`. `--archetypes explore,devil-advocate,dead-end-analysis` rotates archetypes per replica. `--models opus,sonnet,haiku` rotates models per replica. `elmer batch` gains the same flags, applying per topic.

3. **Synthesis trigger.** In `_refresh_running()`, when a replica completes, check if all siblings are done. If so, automatically spawn the `elmer-meta-synthesize` agent on a new branch. The agent reads all replica PROPOSALs and writes a consolidated PROPOSAL.md. The synthesis enters the normal review queue.

4. **Lifecycle cascade.** Approving a synthesis auto-declines and cleans up all replicas. Declining a synthesis declines all replicas. Replicas are hidden from `elmer review` — only synthesis proposals are presented for review. `approve --all` skips replicas.

5. **Agent.** `elmer-meta-synthesize` is distinct from the digest agent. Digest does cross-topic convergence; synthesis does same-topic consolidation. The synthesis agent finds consensus, resolves contradictions, fills gaps, and preserves specificity from each proposal.

6. **Daemon.** New step between harvest and gate: check for ready ensembles and trigger synthesis. Best-effort — synthesis failure never blocks the cycle.

7. **MCP.** `elmer_explore` and `elmer_batch` tools gain `replicas`, `archetypes`, and `models` parameters.

8. **Config.** `[ensemble]` section: `synthesis_model`, `synthesis_max_turns`, optional `default_replicas` and `default_archetypes`.

**Key design choices:**

- Default is same-archetype for all replicas (simple). `--archetypes` overrides for diversity. No magic rotation.
- Budget is divided by N+1 (replicas + synthesis share).
- Replicas are never individually approved — only the synthesis.
- Each replica runs independently with no knowledge of others. Independence is the whole point.

**Alternatives considered:** Running replicas sequentially and feeding each into the next (loses independence, becomes iterative refinement — that's what `elmer amend` does), best-of-N selection without synthesis (wastes the unique insights in non-selected proposals), a separate `ensembles` table with its own lifecycle (adds complexity — deriving status from components is sufficient), automatic ensemble for all explorations (wasteful — ensemble is for high-ambiguity topics where the extra cost is justified).

## ADR-032: Archive as Source of Truth for Completed Explorations

**Decision:** The proposal archive (`.elmer/proposals/`) becomes the source of truth for completed explorations. The SQLite database tracks only in-flight state. Three changes enforce this:

1. **Auto-clean on approve and decline.** `approve_exploration()` and `decline_exploration()` now delete the DB record after archiving. The archive file — with its self-describing metadata header — is the permanent record. `--no-clean` flag retains the old behavior for inspection. `clean` becomes a garbage collector for failed explorations and crash recovery, not a required workflow step.

2. **Archive-aware slug uniqueness.** `_make_unique_slug()` checks both the database and `.elmer/proposals/` for existing slugs. After clean deletes a DB record, the archive file prevents slug reuse. A re-explored topic gets `-2`, `-3`, etc., keeping IDs, branches, archives, and logs unique.

3. **Archive-aware digest synthesis.** `digest.py` reads directly from archive metadata headers instead of cross-referencing with the DB. `_parse_archive_metadata()` extracts fields from the HTML comment header. `_read_approved_proposals()` and `_read_declined_proposals()` merge DB records (in-flight) with archive metadata (completed). `approvals_since_last_digest()` counts both sources. Digests now work correctly regardless of when `clean` runs.

**Context:** Two bugs, one root cause. Bug 1: after `clean` deleted a DB record, re-exploring the same topic reused the slug and silently overwrote the archived proposal — data loss. Bug 2: digests iterated DB records to find archive files; after `clean`, those records were gone, so digests couldn't read archived proposals — silent data loss in convergence synthesis.

The root cause was an inconsistent source of truth. The archive was designed to be permanent and self-describing (metadata header with id, topic, archetype, model, status), but the digest treated the DB as the only index. The archive had no reader that parsed its metadata — it was write-only.

**Archive metadata now includes:** `id`, `topic`, `archetype`, `model`, `status`, `decline_reason` (if declined), `merged_at` (if approved), `completed_at`, `archived` (timestamp).

**`clean` role change:** Previously required after approve/decline to free DB records and worktrees. Now reduced to maintenance: cleaning failed explorations, recovering from crashes, pruning orphaned worktrees. Projects that ran before ADR-032 have accumulated approved/declined records; `clean` handles those on next run.

**Alternatives considered:** Soft delete (add `cleaned_at` column, filter in queries — preserves full DB history but touches every query), archive filenames with timestamps instead of IDs (collision-proof but breaks the ID-to-filename mapping that digests rely on), only fixing the archive overwrite without changing the digest (leaves the digest broken after clean).
