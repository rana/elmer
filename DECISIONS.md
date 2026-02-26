# Elmer — Decisions

Architecture Decision Records. Mutable living documents — update directly when decisions evolve. When substantially revising an ADR, add `*Revised: [date], [reason]*` at the section's end. Git history serves as the full audit trail.

49 ADRs recorded.

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
| ADR-033 | Safety | Archive-before-destroy and crash-recovery resilience |
| ADR-034 | Safety | Commit PROPOSAL.md to branch on completion |
| ADR-035 | UX | Topic visibility in status display |
| ADR-036 | Storage | Topic-derived proposal archive filenames |
| ADR-037 | Naming | Shorter slugs, explicit replica numbering, bounded archive filenames |
| ADR-038 | Safety | Pre-merge verification hooks with auto-amend |
| ADR-039 | Process | Milestone decomposition and autonomous implementation |
| ADR-040 | Intelligence | Cross-step context, plan loading, fallback verification |
| ADR-041 | Safety | Dependency cascade, proposal validation, verification guard |
| ADR-042 | Intelligence | Prerequisites, artifact flow, greenfield decomposition |
| ADR-043 | Safety | Verify-cmd visibility and amend cost attribution |
| ADR-044 | Resilience | Context budget, plan completion verification, worktree setup commands |
| ADR-045 | Operations | Session watchdog, failure-aware retry, per-step model routing |
| ADR-046 | Quality | Plan validation, merge conflict recovery, daemon plan auto-approve |
| ADR-047 | Resilience | Parallel conflict detection, daemon auto-retry for plan steps |
| ADR-048 | Observability | Dependency visibility and cost observability |
| ADR-049 | Safety | Retry dependency repair, pre-approval plan completion check |
| ADR-050 | Execution | Amend failure pattern detection — fail fast on systemic issues |
| ADR-051 | Simplification | Remove budget enforcement — delegate to Claude CLI |
| ADR-052 | Architecture | Decompose implement.py into decompose, plan, implement |
| ADR-053 | Simplification | Remove template mode — agent-only resolution |
| ADR-054 | Safety | Daemon per-cycle approval limits |
| ADR-055 | Operations | Tighten auto-approve criteria for doc-only projects |
| ADR-056 | Verification | Document-coherence verification for doc-only projects |
| ADR-057 | Correctness | NULL cost handling — distinguish $0.00 from missing data |
| ADR-058 | Operations | Stale pending exploration TTL with auto-cancel |
| ADR-059 | Observability | Verification failure counter per exploration |
| ADR-060 | Observability | Verification execution time tracking |
| ADR-061 | UX | Plan step duration estimation |
| ADR-062 | Resilience | Daemon stuck state prevention and partial plan rollback |
| ADR-063 | Quality | FIFO approval ordering and normalized failure detection |
| ADR-064 | Integration | Custom skills as verification hooks (F3) |
| ADR-065 | Operations | External dependency tracking with blockers (D4) |
| ADR-066 | Resilience | Stale PID recovery and cascade failure alerting |

---

## ADR-001: Git Worktrees Over Directory Copying

**Decision:** Use git worktrees for branch isolation, not directory copying.

Worktrees share `.git`, are instant to create, and space-efficient. Directory copying wastes disk, duplicates git history, and creates confusion about which copy is canonical. Worktrees provide real branch isolation with minimal overhead.

**Alternatives considered:** Directory copying (cp -r), temporary git clones.

## ADR-002: Claude Invocation Patterns

**Decision:** Two invocation patterns for `claude -p`, both using `--output-format json`:

- **Background** (`spawn_claude`): Explorations. Long-running, PID-tracked, output to log files. Agent Teams were rejected — they're session-scoped and don't persist. Elmer explorations should outlive any single session.
- **Synchronous** (`run_claude`): Meta-operations (topic generation, auto-approve review, prompt generation, archetype selection, insight extraction, question mining, invariant validation). Short-lived (3-5 turns), output parsed immediately by the caller.

**Cost extraction:** All invocations use `--output-format json`. Synchronous operations parse JSON from captured stdout. Background workers write JSON to log files, parsed after completion by `parse_log_costs()`. Cost data is stored in SQLite. JSON parsing is best-effort: if it fails, cost fields are left NULL. Cost tracking never blocks exploration flow.

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

## ADR-033: Archive-Before-Destroy and Crash-Recovery Resilience

**Decision:** Strengthen the archive contract from "best-effort, never blocks" to "archive is mandatory; cleanup is blocked by archive failure." Three changes to `_archive_proposal` and its callers in `gate.py`:

1. **Idempotency.** Before attempting to archive, check if `.elmer/proposals/<id>.md` already exists. If so, return the existing path immediately. This handles crash recovery: if a previous `approve` attempt archived the proposal but crashed before completing cleanup, the second attempt doesn't fail because the worktree is gone — it finds the existing archive.

2. **Git-branch fallback.** When the worktree is gone (deleted in a prior crashed attempt), try reading `PROPOSAL.md` from the git branch via `git show <branch>:PROPOSAL.md`. The branch may survive worktree deletion if the crash happened between `git worktree remove` and `git branch -D`. Added `worktree.read_file_from_branch()` for this.

3. **Archive validation before cleanup.** In `approve_exploration`, if archiving the synthesis proposal fails (all recovery strategies exhausted) and the worktree still exists, the function preserves the worktree and warns loudly instead of destroying the only copy. Status is still updated to "approved" (the merge already happened), but the worktree is left for manual recovery.

4. **Cascade sleep hardening.** Ensemble approve/decline cascades now sleep 1.0s before *every* worktree removal, including the first replica (which follows immediately after the synthesis worktree removal). Previously, the sleep only applied to the second replica onward (`if i > 0`), leaving no gap between synthesis cleanup and first replica cleanup — a burst of 6 worktree removals in <1s overwhelmed IDE inotify watchers.

**Context:** Real-world ensemble approval with 5 replicas + 1 synthesis. First `approve` attempt merged the synthesis branch, then crashed during the cascade of 6 worktree removals (inotify storm crashed all VSCode windows, killing the terminal process). Second attempt hit the crash-recovery path ("Branch already merged"), found the synthesis worktree gone, silently failed to archive the synthesis proposal (`_archive_proposal` returned `None` with no warning), cleaned up all replica worktrees (also without archiving), and reported success. Result: all ensemble work lost, no PROPOSAL.md saved to `.elmer/proposals/`, success message displayed.

Root cause chain: (1) `_archive_proposal` silently returned `None` on failure, (2) no fallback to read from git branch/history, (3) no idempotency check for existing archives, (4) callers never checked the return value, (5) cleanup proceeded regardless of archive status, (6) cascade sleep was insufficient and didn't cover the synthesis→first-replica gap.

**Principle:** Archive before destroy. Verify archive succeeded before proceeding with cleanup. If archive fails and the worktree exists, preserve it — a preserved worktree is recoverable; a destroyed one is not. Warn loudly on any fallback or failure. "Best-effort" is acceptable for metadata enrichment (insights, costs), not for the proposal itself.

**Alternatives considered:** Transactional archive+cleanup (too complex for subprocess-based git operations), archive to git instead of filesystem (adds git commits to main branch for internal bookkeeping), two-phase cleanup where all archives are validated before any worktree is destroyed (cleaner but requires restructuring the cascade loop — deferred for now).

## ADR-034: Commit PROPOSAL.md to Branch on Completion

**Decision:** When an exploration transitions from `running` to `done` (or `amending` to `done`), automatically `git add && git commit` PROPOSAL.md to the exploration branch inside its worktree. This ensures the proposal is tracked by git and recoverable via `git show <branch>:PROPOSAL.md` even after the worktree is removed.

**Implementation:** `worktree.commit_proposal_to_branch()` runs in the worktree's working directory:
1. Checks if PROPOSAL.md exists
2. Checks `git status --porcelain PROPOSAL.md` — skips if already tracked and unchanged
3. Runs `git add PROPOSAL.md && git commit -m "Save PROPOSAL.md for <id>"`
4. Returns True if committed, False if skipped or failed (best-effort, never blocks)

Called from `review._refresh_running()` at both transition points (running→done, amending→done), immediately before the status update.

**Context:** ADR-033 added a git-branch fallback to `_archive_proposal()` — reading PROPOSAL.md from the branch via `git show` when the worktree is gone. But this fallback was dead code: PROPOSAL.md was never committed to the branch. Exploration agents write PROPOSAL.md via Claude Code's `Write` tool, which creates an untracked file. When `git worktree remove --force` runs, untracked files are permanently destroyed. The git-branch fallback in ADR-033 only works if the file is tracked — which it never was.

This was the root cause of unrecoverable data loss in the ensemble incident: even with ADR-033's multi-strategy archive, PROPOSAL.md could not be recovered from git because it was never committed.

**Scope:** Only PROPOSAL.md is committed. Other files the agent may create (scratch files, test outputs) are not committed — they are not archival artifacts. The commit happens on the exploration branch (inside the worktree), not on main. The commit is cleaned up along with the branch when the exploration is approved or declined.

**Interaction with ADR-029:** When an exploration is approved, `merge_branch()` brings PROPOSAL.md into main, then `remove_file_and_commit()` deletes it (PROPOSAL.md is an elmer artifact, not a project deliverable). With commit-on-completion, this sequence now works correctly: the file exists on the branch (committed), gets merged to main, then is deleted. Previously, PROPOSAL.md only appeared on main if the agent happened to commit it — inconsistent and agent-dependent.

**Interaction with ADR-033:** The git-branch fallback in `_archive_proposal()` is now operational. If the worktree is gone but the branch survives (crash between `git worktree remove` and `git branch -D`), the proposal is recoverable from the branch. This closes the last gap in the archive-before-destroy safety chain.

**Alternatives considered:** Instructing agents to commit PROPOSAL.md in their prompts (unreliable — agents may forget or commit to wrong branch), committing at archive time instead of completion time (too late — the point is to ensure the file is tracked before any cleanup can run), committing all files in the worktree (over-broad — scratch files shouldn't be committed).

## ADR-035: Topic Visibility in Status Display

**Decision:** Make the original topic text visible in `elmer status` and ensure all MCP tools return topic data consistently. Three changes:

1. **Ensemble headers show topic text.** The `ENSEMBLE:` header in `show_status()` now displays the original topic from the first replica instead of the ensemble_id slug. The slug is a lossy transformation (lowercased, punctuation-stripped, truncated to 60 chars) — the original topic is always more informative.

2. **Topic subtitle for standalone explorations.** When an exploration's `slugify(topic) != id` — meaning the ID acquired a collision suffix or differs from the raw slug — a second indented line displays the original topic text. This triggers automatically: no user action needed, no extra flag required. Covers the exact cases where the ID has lost differentiating information (e.g., `explore-act-2` and `explore-act-3` exploring different questions).

3. **`-v/--verbose` flag.** `elmer status -v` always shows topic subtitles for all explorations, even when the slug matches the ID. For users who want full context at a glance.

4. **MCP consistency.** `elmer_explore()` now returns `topic` in single-exploration mode (it already did in ensemble mode). All read tools (`elmer_status`, `elmer_review`, `elmer_tree`) already returned topic.

**Context:** The exploration ID is `slugify(topic)` — a URL/branch-safe transformation of the topic text. When different explorations share the same archetype and have short or generic topics, their IDs become nearly identical (e.g., `explore-act`, `explore-act-2`, `explore-act-3`). The status display showed only the ID, never the original topic. The topic was stored in SQLite (`explorations.topic TEXT NOT NULL`) but the CLI display discarded it. The MCP server returned topic in most tools but inconsistently omitted it from single-exploration spawn results.

**Heuristic:** `_topic_adds_info(topic, id)` compares `slugify(topic)` against the exploration ID. When they differ — collision suffix (`-2`, `-3`), truncation, or any slug mismatch — the topic subtitle appears automatically. This is deterministic, zero-configuration, and targets exactly the cases where differentiation is lost.

**Alternatives considered:** Adding a TOPIC column to the status table (screen width already tight at 82 columns — a new column would compress ID to uselessness or require horizontal scrolling), user-supplied `--name` parameter for explorations (correct long-term solution but adds a new concept, schema column, and cognitive overhead — deferred), embedding archetype in the slug (makes branch names longer without solving the core readability problem), replacing the ID column with topic (users need the ID to type into commands like `elmer approve`).

## ADR-036: Topic-Derived Proposal Archive Filenames

**Decision:** Two changes to proposal archiving in `.elmer/proposals/`:

1. **Archive filenames derive from the topic, not the exploration ID.** `_archive_proposal()` uses `slugify(topic, max_length=140)` to generate filenames instead of the exploration ID. This produces human-readable filenames when browsing the proposals directory. Synthesis proposals get a `-synthesis` suffix. Collisions are resolved with a numeric counter, and idempotency is preserved by checking the metadata `id:` field in existing files.

2. **Replica proposals are not archived on synthesis cascade.** When a synthesis is approved or declined, replica proposals are no longer archived — only worktrees and DB records are cleaned up. The synthesis proposal is the permanent record and already embeds all replica content verbatim in its prompt. Individual replica content is also recoverable from git history if needed.

**Context:** The archive filename was coupled to the exploration ID (`{id}.md`), which is itself a `slugify(topic, max_length=60)` derivative. This worked for standalone explorations with distinctive topics (`what-is-contributing-to-cognitive-load.md`) but failed for ensembles: replicas of the same topic produced near-identical filenames differentiated only by numeric suffix (`explore-act.md`, `explore-act-2.md`, `explore-act-3.md`). These names conveyed no information when browsing the proposals directory.

Archiving 5 replica proposals alongside the synthesis also created noise. The synthesis already incorporated all replica content, making the individual replica archives redundant.

**Implementation changes:**
- `gate.py`: New `_resolve_archive_path()` and `_archive_has_id()` helpers. `_archive_proposal()` uses topic-derived filenames with collision handling and idempotency detection via metadata inspection.
- `gate.py`: Replica `_archive_proposal()` calls removed from both `approve_exploration()` and `decline_exploration()` ensemble cascade loops.
- `explore.py`: `_make_unique_slug()` checks `.elmer/logs/{slug}.log` instead of `.elmer/proposals/{slug}.md` for slug reuse prevention (ADR-032). Log files are still slug-based; proposal filenames no longer are.

**Interaction with ADR-032:** Slug reuse prevention now keys off log files instead of proposal archives. Logs remain slug-based (`{id}.log`) and persist after DB cleanup, preserving the ADR-032 guarantee.

**Interaction with ADR-033:** The archive-before-destroy safety chain is unchanged for standalone explorations and synthesis. For replicas in the cascade path, destruction proceeds without archiving — this is intentional, not a gap.

**Alternatives considered:** Increasing `slugify()` max_length only (partial fix — replicas still get meaningless suffixes), `{id}--{archetype}.md` format (helps multi-archetype ensembles but not same-archetype replicas), subdirectories per ensemble (premature structure for current scale).

## ADR-037: Shorter Slugs, Explicit Replica Numbering, Bounded Archive Filenames

**Decision:** Three changes to naming:

1. **Slug default max_length reduced from 60 to 40 characters (~5-6 words).** The previous 60-char limit produced 10+ word slugs that were always truncated in status display and painful to type in commands. At 40 chars, slugs preserve enough discriminating words to distinguish topics at a glance while staying manageable as identifiers. The full topic text is always available via ADR-035 subtitles and the DB. Collision risk is handled by `_make_unique_slug()` counters.

2. **Ensemble replicas are explicitly numbered `-1` through `-N`.** `start_ensemble()` passes a `slug_override` to `start_exploration()` for each replica, producing `{ensemble_id}-1`, `{ensemble_id}-2`, etc. Previously, the first replica inherited the bare slug through collision-free resolution while replicas 2+ got `-2`, `-3` suffixes via `_make_unique_slug()` counter starting at 2.

3. **Synthesis archive filenames use `ensemble_id`, not topic text.** `_resolve_archive_path()` generates synthesis archive filenames as `{ensemble_id}-synthesis.md` instead of `slugify(topic, max_length=140) + "-synthesis"`. The `ensemble_id` is already a bounded slug (max 40 chars from `slugify()`), giving synthesis archives a maximum filename of ~53 characters. Non-synthesis archive filenames use `max_length=60`.

**Problems fixed:**
- Slugs were too long to type or scan, but too short to preserve full topics — a dead zone.
- Visual inconsistency: replica 1 lacked a suffix while replicas 2+ had one.
- Identity collision: `ensemble_id` and replica 1's `id` were the same string.
- Topic subtitle inconsistency: `_topic_adds_info()` suppressed the subtitle for replica 1 but showed it for replicas 2+ — now consistent across all replicas.
- Synthesis archive filenames exceeded reasonable filesystem length limits.

**Implementation:**
- `explore.py`: `slugify()` default `max_length` changed from 60 to 40. `start_exploration()` gains `slug_override` parameter. `start_ensemble()` generates `{ensemble_id}-{i+1}` for each replica.
- `gate.py`: `_resolve_archive_path()` uses `ensemble_id` for synthesis archives. Non-synthesis archive `max_length` set to 60.

**Solo explorations unaffected by replica numbering.** They still use collision-based naming via `_make_unique_slug()`. The shorter slugs apply universally.

**No migration required.** Existing explorations keep their names. New ones get shorter slugs. Status display groups by `ensemble_id` and `ensemble_role`, not by slug pattern.

**Interaction with ADR-035:** Shorter slugs mean `_topic_adds_info()` triggers more often (truncated slug ≠ full topic slug), surfacing topic subtitles where they're most useful.

**Interaction with ADR-036:** Archive filenames bounded at 60 chars (non-synthesis) or ~53 chars (synthesis via ensemble_id), down from the previous 140+.

## ADR-038: Pre-Merge Verification Hooks with Auto-Amend

**Decision:** Add verification hooks that run shell commands after an exploration session completes but before the `done` transition. On failure, automatically amend the exploration with the failure output as feedback. This transforms Elmer from a research tool into a build tool — explorations that produce code can be validated before human review.

**Architecture:**

1. **Verification command sources.** Two levels, per-exploration overriding global:
   - Per-exploration: `--verify-cmd "pytest"` on `elmer explore`, stored in `explorations.verify_cmd`
   - Global: `[verification] on_done = "make test"` in `config.toml`, applied to all explorations without an explicit verify_cmd

2. **Execution point.** In `review._refresh_running()`, after PROPOSAL.md exists and is committed to the branch (ADR-034), but before the status transitions to `done`. The verification runs in the worktree directory, which contains the full project with the exploration's changes on top — the correct CWD for testing code that hasn't been merged yet. Timeout: configurable via `[verification] timeout = 300` (default 300 seconds). Output truncated to 3000 characters.

3. **Auto-amend on failure.** When verification fails (exit code ≠ 0), the system automatically amends the exploration with structured feedback containing the command, exit code, and full output. The amend agent (existing `elmer-meta-amend`) receives this context and fixes the code. After amendment completes, the next `_refresh_running()` cycle re-runs verification in the amending → done transition path — creating a correct fix loop. This re-verification is critical: without it, the auto-approve bypass would assume verification passed when it was never re-checked after the amend. The amending path also adds the exploration to `newly_done` so auto-approve triggers correctly.

4. **Retry budget.** `[verification] max_retries = 2` in config (default). `state.increment_amend_count()` tracks attempts per exploration. When retries are exhausted, the exploration is marked `failed`. If the exploration belongs to an implementation plan (`plan_id`), the plan is paused.

5. **Schema additions.** Three new columns on `explorations`: `verify_cmd TEXT`, `plan_id TEXT`, `plan_step INTEGER`, `amend_count INTEGER DEFAULT 0`. Migration is additive — existing databases gain columns automatically.

**Why pre-merge, not post-merge:** The `--on-approve` chain action (ADR-012) runs after merge — too late. By the time a test failure is detected post-merge, the broken code is already on the target branch. Verification hooks run before any approval decision, keeping the target branch clean.

**Why shell commands, not a plugin system:** Shell commands provide maximum composability. `pytest`, `make test`, `cargo check`, `npm run build` — any project's existing validation toolchain works without adaptation. The verification command is the project's own quality gate, not an Elmer-specific abstraction.

**Security model:** Verification commands are user-specified only (via CLI flag or config file). They are never AI-generated. This is consistent with ADR-012's chain action constraint: "chain actions are user-specified only — never auto-generated by AI."

**Interaction with auto-approve gate:** When an exploration has a `verify_cmd` and reaches `done` status, verification has already passed (failed verification marks status as `failed`, not `done`). Verification-passing explorations bypass the AI review gate entirely and auto-approve directly. This is correct because: (1) verification is deterministic proof the code works, (2) the AI review gate's criteria (e.g., "document-only proposals") would incorrectly reject code changes from implementation steps, (3) the verification command is the project's own quality gate — a stronger signal than an AI's opinion.

**Interaction with ADR-028:** Auto-amend reuses the existing amendment workflow (`amending` → `done`). The verification hook adds a new trigger for amendments (verification failure) alongside the existing trigger (human editorial feedback). The amend agent is the same — it receives structured feedback and revises accordingly.

**Interaction with ADR-034:** Commit-on-completion ensures PROPOSAL.md is tracked on the branch before verification runs. If verification triggers auto-amend, the amend agent can read the existing PROPOSAL.md from git.

**Alternatives considered:** Post-merge hooks (too late — broken code on target branch), pre-commit git hooks in the worktree (wrong scope — these are project-level validations, not commit-level), a dedicated verification agent instead of shell commands (overkill — existing test suites are better validators than AI), no auto-amend — just fail and require manual retry (wastes the opportunity for self-healing — most verification failures are fixable).

## ADR-039: Milestone Decomposition and Autonomous Implementation

**Decision:** Add `elmer implement "Milestone 1a"` — a command that decomposes a milestone into ordered implementation steps, asks clarifying questions upfront, and executes the steps as chained explorations with per-step verification hooks (ADR-038). This extends Elmer from autonomous research into autonomous implementation.

**Architecture:**

1. **Four-phase flow:** Decompose → Clarify → Execute → Report.

2. **Decompose.** The `elmer-meta-decompose` agent (opus model, `Read/Grep/Glob/Bash` tools) reads ROADMAP.md, DESIGN.md, DECISIONS.md, and scans the filesystem. It produces a structured JSON plan:
   ```json
   {
     "milestone": "Milestone 1a",
     "steps": [
       {
         "title": "Initialize Next.js project",
         "topic": "Set up Next.js 15 with...",
         "verify_cmd": "npm run build",
         "depends_on": [],
         "archetype": "implement"
       }
     ],
     "questions": ["Which auth provider?"]
   }
   ```
   Each step has a title, full topic (the exploration prompt), optional verification command, dependency list (indices into the steps array), and archetype (defaults to `implement`).

3. **Clarify.** If the decompose agent produced questions, `elmer implement` presents them interactively. User answers are injected into all step topics as a `## Context from user` section. Three non-interactive paths: `--yes/-y` skips clarification entirely, `--answers-file answers.json` loads pre-answered questions from a JSON or TOML file (key: question index, value: answer string), `--dry-run` shows the plan without executing. `--dry-run --save` persists the plan to `.elmer/plans/` for later execution without re-running decomposition.

4. **Execute.** Each step becomes a chained exploration (`elmer explore` with `--verify-cmd`, `depends_on`, `plan_id`, `plan_step`). Steps execute in dependency order — each waits for its dependencies to be approved and merged before starting. Chain mode (sequential by default, `--max-concurrent` for parallelism within dependency constraints). Auto-approve is on by default for implementation plans.

5. **Report.** `elmer implement --status` shows plan progress with per-step status icons (`.` pending, `~` running, `*` done, `+` approved, `!` failed). `--resume PLAN_ID` retries failed steps. The daemon checks plan completion in its cycle (step 6c in `_run_cycle`).

**New module: `implement.py`.** Functions: `decompose_milestone()`, `execute_plan()`, `get_plan_status()`, `show_plan_status()`, `resume_plan()`. Helper functions: `_read_project_context()`, `_scan_filesystem()`, `_parse_plan_json()`, `_inject_answers()`.

**New schema: `plans` table.**
```sql
plans (
    id TEXT PRIMARY KEY,
    milestone_ref TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    total_cost_usd REAL DEFAULT 0
)
```
Plan status is derived from step statuses: all approved → completed, any failed → paused. Plans are lightweight wrappers — the real state lives in the explorations table.

**New agents:**
- `elmer-meta-decompose` — opus model, reads project docs, produces JSON plan. 10 rules for decomposition quality (no step > 100 lines changed, every step has verify_cmd, dependencies are acyclic, etc.).
- `elmer-implement` — exploration agent with `Read/Grep/Glob/Bash/Edit/Write`. Self-verification instructions: run build/test/lint before writing PROPOSAL.md.

**MCP tools:** `elmer_implement` (decompose + execute, supports dry_run) and `elmer_plan_status` (plan progress query). Both follow existing MCP design principles — wrapping core module functions, stateless, per-call DB connections.

**Daemon integration:** Step 6c in `_run_cycle()` calls `impl_mod.get_plan_status()` to check for completed plans and log completion. Plans auto-pause on step failure; `elmer implement --resume` retries failed steps.

**Why chain mode by default:** Implementation steps build on each other. Step 2 modifies files created by Step 1. Without chaining, parallel steps would create merge conflicts. `--max-concurrent` overrides for plans with independent steps (the decompose agent can specify `depends_on` per step).

**Why opus for decomposition:** The decompose agent reads 5000+ lines of project documentation and produces a multi-step implementation plan with verification commands. This is an architectural reasoning task where opus's deeper reasoning justifies the cost. Execution steps use the configured model (configurable, defaults to opus).

**Context continuity across steps:** Each step runs in its own worktree with a fresh Claude context window. It sees the cumulative codebase (all previous steps merged) because chain mode merges before the next step starts. User answers from the clarify phase are injected into every step's topic, providing consistent context without cross-step prompt leakage.

**Alternatives considered:** A single long-running exploration for the whole milestone (context window limits, no intermediate checkpoints, no verification between steps), human-in-the-loop between every step (defeats autonomy — verification hooks handle quality gates), a custom execution engine separate from explorations (unnecessary — explorations with chaining and verification already provide the right primitives), allowing the decompose agent to auto-execute without user review of the plan (violates conservative defaults — `--dry-run` and the clarify phase are safety valves).

## ADR-040: Cross-Step Context Injection, Plan Loading, and Fallback Verification

**Decision:** Three interconnected improvements to the implementation pipeline that address information flow between steps, workflow efficiency, and verification resilience.

### Cross-Step Context Injection

**Problem:** Each implementation step runs in a fresh Claude context window with only its own topic text. Steps have no awareness of the plan they belong to, what previous steps accomplished, or what's coming next. This leads to redundant work, missed integration points, and contradictory approaches between steps.

**Solution:** `_build_step_context()` in `implement.py` builds a structured context block injected into each step's topic at execution time. Contains:

1. **Position** — "Step 2 of 7 in milestone X, Plan ID: Y"
2. **Previous steps** — status, proposal summary (truncated to 200 chars), files changed (from branch diff for approved steps)
3. **Upcoming steps** — titles only, providing awareness of what's next without constraining implementation

The context block is appended to the step's topic (not prepended) so the step's own instructions remain primary. Status icons match the existing convention (`.` pending, `~` running, `*` done, `+` approved, `!` failed).

**Why dynamic, not static:** Context is built at execution time by querying the plans table and explorations table. This means later steps see the actual results of earlier steps (summaries, files changed) rather than predicted outcomes from the decompose phase. If a step is re-executed after amendment, it sees the updated state.

### Plan Loading and Partial Execution

**Problem:** `elmer implement "Milestone X"` always calls the decompose agent (opus model, ~$0.50-2.00). During iterative development — adjusting a plan, re-running failed steps, or testing specific steps in isolation — re-decomposition is wasteful and non-deterministic (the agent might produce a different plan).

**Solution:** Two new CLI options:

- `--load-plan FILE` — loads a saved plan JSON (from `--dry-run --save` or hand-edited), skips decomposition entirely. The plan file is the source of truth.
- `--steps SPEC` — runs only specific steps. Supports three formats: single (`0`), comma-separated (`0,2,5`), and ranges (`0-3`, which expands to `0,1,2,3`). Can combine: `0,3-5` runs steps 0, 3, 4, 5.

**New function:** `load_plan(plan_path: Path) -> dict` in `implement.py`. Validates the plan has a `steps` key. Returns the same dict structure as `decompose_milestone()`.

**Workflow this enables:**
```bash
elmer implement "Milestone 1a" --dry-run --save     # Decompose once
# Edit .elmer/plans/milestone-1a.json if needed
elmer implement --load-plan .elmer/plans/milestone-1a.json --steps 0   # Test step 0
elmer implement --load-plan .elmer/plans/milestone-1a.json --steps 1-3 # Run steps 1-3
```

### Fallback Verification

**Problem:** When verification exhausts all amend retries, the exploration is marked as failed and the plan is paused. But the verification command may be overly strict — e.g., `npm test && npm run lint` fails on a linting rule while all core tests pass. The step's code might be sound enough to continue the plan.

**Solution:** A two-tier verification strategy via `[verification] fallback` in config:

```toml
[verification]
on_done = "npm test && npm run lint"
fallback = "npm run build && npm test"
timeout = 300
max_retries = 2
```

When the primary `on_done` command exhausts retries and the exploration would be marked as failed, the fallback command runs. If the fallback passes, the exploration transitions to "done" (and continues through auto-approve). If the fallback also fails, the exploration is marked failed and the plan is paused as before.

**Applied at both transition points:** running → done and amending → done. The fallback is a last resort — it runs only after all amend retries against the primary command are exhausted.

### Enriched Amend Feedback

**Problem:** When auto-amend fires for a plan step, the amend feedback contains only the verification failure output. The implementation session has no awareness of the plan context — which step this is, what goal it's trying to achieve, or what previous steps accomplished. This leads to unfocused fixes.

**Solution:** `_attempt_auto_amend()` in `review.py` queries the plan and exploration tables (best-effort) when the exploration has a `plan_id`. Injects a `## Plan Context` section into the amend feedback containing: step position, step title and goal, and summaries of completed previous steps.

**Files modified:** `implement.py` (cross-step context, plan loading), `cli.py` (--load-plan, --steps wiring), `review.py` (fallback verification, enriched amend feedback).

**Why not an MCP tool for plan state queries:** The cross-step context injection and enriched amend feedback provide the most useful plan information at exactly the right moments. Adding an MCP tool for ad-hoc plan queries would add complexity without improving the common case. If specific steps need to query plan state during execution (not just at start), an MCP tool would be warranted — deferred until evidence shows the need.

## ADR-041: Failed Dependency Cascade, Proposal Validation, and Verification Guard

**Decision:** Three safety improvements that close feedback loops in the autonomous pipeline: failed dependency cascade prevents silent deadlocks, proposal structural validation catches malformed output before auto-approve, and the verification auto-approve guard adds a diff-size check and configurability to the verification shortcut.

### Failed Dependency Cascade

**Problem:** When an exploration fails or is declined, any pending exploration that depends on it is stuck forever. `get_pending_ready()` checks `dep.status != 'approved'` — a failed dependency will never become approved, so the dependent exploration never becomes "ready." In plans with 10+ steps, a failure in step 3 orphans steps 4-10 silently.

**Solution:** New query `get_pending_blocked()` in `state.py` finds pending explorations with at least one failed or declined dependency. `schedule_ready()` in `explore.py` calls this first and cascades the failure: blocked explorations are marked as failed with a summary noting which dependency failed. If the blocked exploration belongs to a plan, the plan is paused.

**Why cascade eagerly:** The alternative is leaving pending explorations in limbo and relying on the user to notice. In autonomous mode, silent deadlocks are the worst failure mode — the system appears idle when it's actually stuck. Cascading immediately surfaces the failure in `elmer status` and triggers plan pausing.

**Why not auto-retry:** Dependency failure usually means the upstream work is architecturally wrong, not transiently broken. Auto-retrying the failed dependency would loop. The correct flow is: human reviews the failure, fixes the upstream (via `elmer amend` or `elmer retry`), then `elmer implement --resume PLAN` re-runs the cascade.

### Proposal Structural Validation

**Problem:** The auto-approve gate (AI review or verification shortcut) can approve malformed proposals. An exploration that produces an empty or stub PROPOSAL.md ("# Proposal\nTODO: add content") with a passing test suite will auto-approve and merge garbage into main.

**Solution:** `_validate_proposal_structure()` in `autoapprove.py` runs deterministic structural checks before any approval path:

1. **Not empty** — rejects blank proposals
2. **Minimum length** — at least 100 characters (prevents stub proposals)
3. **No TODO/FIXME/XXX markers** — catches incomplete work the agent left for later
4. **At least one markdown heading** — basic structural sanity

The validation runs before both the verification shortcut and the AI review gate. On failure, the error is recorded in `proposal_summary` so it's visible in `elmer status` and `elmer review`.

**Why not in the AI review prompt:** Structural checks are deterministic and free. Sending an obviously broken proposal to the AI review gate wastes an API call (~$0.02-0.10) and introduces non-determinism (the AI might approve a stub). Fast deterministic gates should run before slow non-deterministic ones.

### Verification Auto-Approve Guard

**Problem:** ADR-038 introduced a verification shortcut: if `verify_cmd` passed, auto-approve skips the AI review entirely. The rationale was "verification is deterministic proof the code works." But this is too permissive — a passing test suite doesn't verify architectural soundness, diff scope, or proposal quality.

**Solution:** Three refinements:

1. **Diff size guard for standalone explorations** — for non-plan explorations with passing verification, check file count against `max_files_changed` (default 10). Small diff + passing tests = safe to shortcut. Large diff = fall through to AI review.

2. **Plan steps bypass diff size guard** — plan steps with passing `verify_cmd` auto-approve regardless of diff size. The decompose agent chose the verify_cmd as the definitive quality gate, and scaffold steps routinely create 20+ files. Without this bypass, greenfield Step 0 would block every plan.

3. **Configurable shortcut** — `[verification] auto_approve_on_pass` (default: `true`). Set to `false` to require AI review for all explorations regardless of verification status.

The `max_files_changed` guard still applies to the AI-review-only path for standalone explorations. Plan steps without `verify_cmd` still go through AI review with no file count limit.

```toml
[verification]
on_done = "npm test && npm run lint"
auto_approve_on_pass = true    # false = always require AI review

[auto_approve]
max_files_changed = 10         # diff size guard (standalone explorations only)
```

*Revised: 2026-02-25, plan steps bypass diff size guard for autonomous operation*

**Files modified:** `state.py` (get_pending_blocked query), `explore.py` (cascade in schedule_ready), `autoapprove.py` (structural validation, verification guard).

## ADR-042: Pre-Flight Prerequisites, Artifact Flow, and Greenfield Decomposition

**Decision:** Three improvements that address the gap between project documentation and operational readiness for AI implementation agents. Focused on greenfield projects where no code exists yet.

### Pre-Flight Prerequisite Validation

**Problem:** `execute_plan()` launches step 0 immediately. If required tools (`node`, `pnpm`) or environment variables (`DATABASE_URL`, `API_KEY`) are missing, the step runs for 10+ minutes, generates code that can't build, fails verification, exhausts amend retries, and wastes $5-20. The failure is predictable and preventable.

**Solution:** Plans can include a `prerequisites` block:

```json
{
  "prerequisites": {
    "env_vars": ["DATABASE_URL", "VOYAGE_API_KEY"],
    "commands": ["node --version", "pnpm --version"],
    "files": ["DESIGN.md"]
  }
}
```

`validate_prerequisites()` in `implement.py` checks all three categories before `execute_plan()` creates any explorations. Failures block execution with clear error messages. `--dry-run` displays prerequisite status.

**Why check files too:** In greenfield projects, design documentation is the input. If DESIGN.md doesn't exist, the implementation agent has nothing to work from. Checking files validates that the project is in the expected state.

**Why not check in each step:** Prerequisites are plan-level concerns. If Step 0 needs `node` but Step 3 needs `VOYAGE_API_KEY`, you want to know both are missing before spending $5 on Steps 0-2. Fail fast, fail completely.

### Key File Artifact Flow

**Problem:** Cross-step context injection (ADR-040) provides proposal summaries and file diffs from previous steps. But when Step 0 scaffolds a greenfield project, the *content* of key files (config, `.env.example`, service interfaces) matters more than the diff stat. Step 1 needs to see `lib/config.ts` to know what constants to use. Step 2 needs to see `lib/services/search.ts` to follow the same patterns.

**Solution:** Steps can declare `key_files` in the plan JSON:

```json
{
  "title": "Scaffold project",
  "key_files": ["package.json", "lib/config.ts", ".env.example"]
}
```

After a step is approved and merged, `_build_step_context()` reads the declared key files from `project_dir` (which now contains the merged code) and injects their content into subsequent steps' context blocks, truncated at 2000 chars per file.

**Why read from project_dir, not the worktree:** By the time the next step starts, the previous step has been approved and merged into main. The worktree may have been cleaned up. `project_dir` always reflects the cumulative state of all merged work.

**Why not inject all changed files:** Most changed files are implementation details. A 500-line React component doesn't help the next step. `key_files` is the decompose agent's signal of "these are the patterns and contracts — the rest is implementation." Keep the context window focused.

### Greenfield Decomposition Rules

**Problem:** The decompose agent's 10 rules were generic. For greenfield projects (0% scaffolded), three critical patterns were implicit:

1. Step 0 must create the build toolchain *and* one example of each architectural pattern
2. `.env.example` must exist from Step 0 with every variable the project will need
3. Prerequisites should distinguish "tools that must exist before coding" from "services that might not be configured yet" (the latter are questions, not prerequisites)

**Solution:** Five new rules (11-15) added to the decompose agent (`agents/decompose.md`) under a "Greenfield Projects" section:

- Rule 11: Step 0 creates foundation + `.env.example` + directory structure; declares `key_files`
- Rule 12: Step 0 creates one real example of each pattern (service, route, test) — subsequent steps follow it
- Rule 13: Declare prerequisites; env vars for external services are questions, not prerequisites
- Rule 14: Separate concerns per step (schema → service → API → frontend → integration)
- Rule 15: Every step that introduces a new env var updates `.env.example`

**Why one example of each pattern matters more than documentation:** AI agents follow patterns by imitation, not by description. Telling an agent "services go in /lib/services/ with zero framework imports" is less effective than showing it an actual service at that path. When Step 0 creates one real service, Steps 1-5 can reference it as `"follow the pattern in /lib/services/embeddings.ts"` — and the `key_files` artifact flow ensures the agent sees the actual content.

**Files modified:** `implement.py` (validate_prerequisites, artifact injection in _build_step_context), `cli.py` (dry-run prerequisite display), `agents/decompose.md` (prerequisite field, key_files field, greenfield rules 11-15).

## ADR-043: Verification Visibility and Amend Cost Attribution

**Decision:** Two improvements that close the loop between the AI agent's awareness of its success criteria and the accuracy of plan-level cost reporting.

### Verification Command Visibility

**Problem:** The implementation agent receives its topic (task description) and cross-step context, but NOT the `verify_cmd` that will judge its work. The agent is told generically to "run build/test/lint" (in the implement archetype instructions), but the actual verification command might be `pnpm test -- --run search.test && pnpm lint`. The agent might skip linting, complete its work, and then fail verification — wasting an amend cycle on something entirely preventable.

**Solution:** `execute_plan()` now injects a `## Verification` block into each step's enriched topic:

```
## Verification

After completing your work, this command will be run to verify it:

    pnpm test -- --run search.test && pnpm lint

Run this command yourself before writing PROPOSAL.md.
```

This gives the agent explicit knowledge of its success criterion. The agent can run the exact command before declaring completion, catching issues before the external verification hook fires.

**Why inject, not just document:** The implement archetype says "run project's build/test/lint commands." But the verify_cmd may be step-specific (e.g., a targeted test file) or include commands the agent wouldn't guess. Explicit injection eliminates guesswork.

### Amend Cost Attribution

**Problem:** When auto-amend fires, the amend session's cost is recorded in the `costs` table as a meta-operation (`operation="amend"`) but NOT added to the exploration's `cost_usd` field. Plan total cost uses `SUM(exp.cost_usd)`, so amend costs are invisible in plan status output.

**Solution:** After an amend session completes and its cost is parsed from the log, the cost is also accumulated into the exploration's `cost_usd`:

```python
current_cost = exp["cost_usd"] or 0.0
state.update_exploration(conn, exp["id"], cost_usd=current_cost + cost_result.cost_usd)
```

This means `exp["cost_usd"]` now represents the true total cost of the exploration (initial + all amends). Plan status display shows accurate per-step and total costs.

**Files modified:** `implement.py` (verify_cmd injection in execute_plan), `review.py` (amend cost roll-up).

*Revised: 2026-02-25, ADR-051 removed plan budget enforcement subsection*

## ADR-044: Context Budget, Plan Completion Verification, and Worktree Setup Commands

**Decision:** Three improvements that address scaling failures in long plans, integration verification gaps when all steps pass, and environment readiness in fresh worktrees.

### Context Budget for Cross-Step Context

**Problem:** `_build_step_context()` (ADR-040) grows linearly with step count. For each previous step, it includes: a status line, a proposal summary (up to 200 chars), file change lists, and key file artifacts (up to 2000 chars each). A 15-step plan at step 14 could produce 30KB+ of context — plus the step's own topic, verify_cmd block, and the implement agent's system prompt. This pushes against or exceeds Claude's effective context window, causing late-plan steps to receive truncated or degraded context.

**Solution:** Three mechanisms in `_build_step_context()`:

1. **Prioritized detail levels** — Steps within the last 3 before the current step, and direct dependency steps, get full detail (summary, file changes, key file artifacts). Older steps are compressed to one-line status summaries. This means step 12 of a 15-step plan sees steps 0-8 as one-liners and steps 9-11 with full detail.

2. **Artifact step limit** — Key file artifacts are collected from at most 3 recent approved steps. Older steps' artifacts are omitted. The most important artifacts are from the most recent steps (which built on the earlier ones).

3. **Hard character budget** — If the total context exceeds `max_context_chars` (default 12,000), key file code blocks are dropped first. If still over budget, the entire context is truncated with a marker. This is a safety net — the prioritization above should keep context well within budget for plans up to ~20 steps.

**Why 12,000 chars default:** The step topic itself can be 1-5KB. The verify_cmd block is ~200 chars. The implement agent's system prompt is ~3KB. The project's CLAUDE.md is injected separately. Total prompt needs to stay well under Claude's context limit. 12KB for cross-step context leaves ample room.

**Why not summarize with AI:** AI summarization adds latency and cost per step launch. The structural compression (one-line for old steps, full for recent) is deterministic, free, and predictable. If an agent needs older context, it can read the project docs or git log.

### Plan Completion Verification

**Problem:** When all plan steps are approved, `get_plan_status()` transitions the plan to "completed." But per-step verification tests in isolation — each step runs its verify_cmd in its own worktree against its own changes. Nothing verifies that the assembled pieces work together. A scaffold step might create a config file; a later step might depend on a key that the scaffold step didn't define. Both steps pass individually, but the integration fails.

**Solution:** `run_completion_check()` in `implement.py` runs after a plan transitions to "completed":

1. **Command resolution** — Uses `completion_verify_cmd` from the plan JSON (preferred), falls back to `[verification] on_done` from config, then to the last step's `verify_cmd`.
2. **Runs in project_dir** — The main branch, where all steps have been merged. This is the true integration environment.
3. **600s timeout** — Longer than per-step verification (300s) because integration tests may be heavier.
4. **Pass/fail handling** — On pass, stores a success note in the plan. On fail, pauses the plan with the error output so the human can investigate.

The daemon's cycle step 6c triggers `run_completion_check()` when a plan is newly completed (detected via `_newly_completed` flag set by `get_plan_status()`).

**Why not auto-fix:** Per-step failures auto-amend because the fix scope is clear (one step's changes). Integration failures could be caused by any step's changes, cross-step interactions, or missing glue code. Automated fix would require understanding the full plan's intent. This is a human review boundary.

### Worktree Setup Commands

**Problem:** Each plan step runs in a fresh git worktree created from the main branch. Gitignored artifacts — `node_modules/`, `.venv/`, `target/`, compiled outputs — don't exist in the worktree. When step 1's worktree is created after step 0 merged `package.json`, the worktree has `package.json` but not `node_modules/`. If the implementation agent doesn't run `pnpm install` first, all imports fail, the build breaks, and verify_cmd fails on something entirely unrelated to the agent's work.

The implement agent *should* run install commands (its system prompt says to), but it doesn't always do so, especially when the topic doesn't mention it. This wastes amend cycles on a deterministic, preventable failure.

**Solution:** Steps can declare `"setup_cmd": "pnpm install"` in the plan JSON. The command runs in the worktree after creation but before the Claude session spawns, in both `start_exploration()` (immediate start) and `launch_pending()` (deferred start). Stored in the `explorations` table so deferred steps remember their setup command.

- **Non-fatal:** If setup_cmd fails, a warning is logged but the exploration still starts. The agent can attempt its own recovery. This avoids blocking on transient install failures (network timeouts, registry hiccups).
- **5-minute timeout:** Long enough for `pnpm install` on a large project, short enough to not stall the pipeline.
- **Idempotent by convention:** Install commands are inherently idempotent. Running `pnpm install` when `node_modules` exists is a no-op.

The decompose agent's rules 16-17 instruct it to set `setup_cmd` on every step after step 0 and to include `completion_verify_cmd` at the plan level.

**Files modified:** `implement.py` (context budget in _build_step_context, run_completion_check, setup_cmd passthrough), `explore.py` (_run_setup_cmd, setup_cmd in start_exploration and launch_pending), `state.py` (setup_cmd column, completion_note column), `daemon.py` (completion check in cycle step 6c), `agents/decompose.md` (setup_cmd and completion_verify_cmd fields, rules 16-17).

## ADR-045: Session Watchdog, Failure-Aware Retry, and Per-Step Model Routing

**Decision:** Three improvements addressing operational liveness, retry quality, and cost optimization in autonomous plan execution.

### Session Watchdog

**Problem:** When `spawn_claude()` launches a background session, there is no timeout. If a Claude session hangs — stuck waiting for an API response, caught in a reasoning loop, or blocked on a tool permission — it remains in "running" status indefinitely. All dependent steps are blocked. The daemon keeps seeing "running" every cycle. The only recovery is manual `elmer cancel ID`.

This is the highest-severity operational gap: a single stuck session silently halts an entire plan pipeline, and in autonomous mode (daemon without human supervision), the system becomes permanently wedged.

**Solution:** Two detection mechanisms added to `_refresh_running()` in `review.py`:

1. **TTL (max session hours):** Compares `created_at` against the current time. Sessions running longer than `[session] max_hours` (default: 4) are terminated via `worker.terminate()` and fall through to the normal process-not-running handling (which marks them as done or failed depending on whether PROPOSAL.md exists).

2. **Log staleness:** Checks the log file's mtime. If the file hasn't been modified in `[session] log_stale_minutes` (default: 60), the session is terminated. Claude writes streaming JSON to the log — if the log isn't being written to, the session is stuck.

After termination, the normal `_refresh_running()` flow handles the exploration: if PROPOSAL.md exists, it transitions to "done" (the agent made progress before hanging); if not, it transitions to "failed" with a diagnosis.

**Configuration:**
```toml
[session]
max_hours = 4              # Max total runtime before auto-kill
log_stale_minutes = 60     # Max time without log output before auto-kill
```

**Why terminate rather than pause:** A hung session consumes system resources (memory, file handles) and may hold locks on the worktree. Terminating is clean. If the session had made partial progress (PROPOSAL.md exists), the verification and amend pipeline can pick it up. If not, failure-aware retry (below) gives the next attempt context about what happened.

**Why not a per-process timer:** `spawn_claude()` uses `subprocess.Popen` — there's no built-in timeout for background processes. Adding `start_new_session=True` means the process outlives the parent. The daemon's periodic `_refresh_running()` is the natural enforcement point.

### Failure-Aware Retry

**Problem:** When `retry_exploration()` re-spawns a failed exploration, it uses the same topic, archetype, model, and parameters. The new session starts completely fresh with zero knowledge of why the previous attempt failed. If the failure was "PROPOSAL.md written to wrong path" or "verification failed: missing database migration," the retry session will likely make the same mistake.

`proposal_summary` already stores the failure diagnosis (from `_diagnose_failure()` in review.py). The information exists — it just wasn't being used.

**Solution:** `retry_exploration()` in `gate.py` now:

1. Reads the failed exploration's `proposal_summary` (failure reason)
2. Optionally reads the session log for the final output snippet (via `review.parse_log_details()`)
3. Appends a `## Previous Attempt Failed` context block to the retry topic:

```markdown
## Previous Attempt Failed

This is a **retry**. The previous attempt failed with:
- Reason: (verification failed: pnpm build && pnpm test)

Final session output (excerpt):
    Error: Cannot find module '@/lib/config'...

**Avoid the approach that caused this failure.**
```

The retry also preserves `setup_cmd`, `verify_cmd`, `plan_id`, and `plan_step` from the original exploration, so plan-level context and worktree setup are maintained across retries.

**Why append to topic, not use a separate parameter:** The topic is the only persistent context the Claude session receives. Adding a separate "retry context" parameter would require changes to `spawn_claude()`, the worker protocol, and every archetype. Appending to the topic is zero-infrastructure.

**Why preserve plan_id/plan_step on retry:** Without this, retried plan steps lose their plan membership. The scheduler won't recognize them as plan steps and cross-step context injection doesn't fire.

### Per-Step Model Routing

**Problem:** All plan steps use the same model (the `--model` flag passed to `execute_plan()`). But step complexity varies enormously:

- Step 0 (scaffold) creates the entire project foundation — it needs the best model (opus)
- Step 5 (add a single API endpoint following an established pattern) is routine — sonnet is sufficient
- Step 8 (complex state machine with edge cases) needs opus again

Using opus for every step wastes ~60% more budget than necessary. Using sonnet for every step risks failures on complex steps that require more reasoning.

**Solution:** Steps can declare `"model": "opus"` in the plan JSON. `execute_plan()` reads `step.get("model", model)` — step-level model takes precedence, falling back to the plan-level default.

The decompose agent's field reference documents when to use opus vs the default: "Step 0 should almost always use opus — it establishes patterns that every subsequent step follows."

The plan display shows model overrides: `Model: opus (override)` when a step uses a different model than the plan default.

**Why not auto-route:** We considered automatic routing based on topic length, number of files mentioned, or dependency count. But these proxies are unreliable — a short topic can describe a complex task, and a long topic might just be detailed instructions for something simple. The decompose agent has the domain knowledge to make this call. It already decides archetype, verify_cmd, and dependencies per step; model is a natural addition.

**Files modified:** `review.py` (watchdog in _refresh_running), `gate.py` (failure context injection in retry_exploration, review import), `implement.py` (per-step model routing in execute_plan, model override display), `agents/decompose.md` (model field in schema and field reference).

## ADR-046: Plan Validation, Merge Conflict Recovery, and Daemon Plan Auto-Approve

**Decision:** Three improvements addressing plan quality assurance before execution, autonomous merge conflict handling, and seamless daemon-driven plan progression.

### Plan Validation in Dry-Run

**Problem:** `--dry-run` only checked prerequisites (env vars, commands, files). A plan with an invalid archetype name, a forward dependency (`step 3 depends on step 5`), or a dependency cycle would pass dry-run and fail expensively at runtime — either immediately (archetype not found) or after several steps complete (cycle detected at scheduling time).

**Solution:** `validate_plan()` in `implement.py` checks:
- **Required fields:** Each step must have a `topic`
- **Archetype existence:** Each step's archetype is resolved via `config.resolve_archetype()` — catches typos and missing custom archetypes before any money is spent
- **Dependency bounds:** All `depends_on` indices must be valid integers within `[0, num_steps)` and must reference earlier steps (no forward or self dependencies)
- **Cycle detection:** Full graph traversal using recursive DFS with an in-stack set. Catches transitive cycles that individual dependency checks would miss.

Wired into the CLI's `--dry-run` path: validation results display before prerequisite checks. Shows "Plan validation: OK (N steps, DAG valid)" or lists specific errors.

**Why not validate on every execution:** `validate_plan()` runs in `--dry-run` and also before `execute_plan()` starts creating explorations. The dry-run gives fast feedback; the execution-time check is the safety net.

### Merge Conflict Recovery for Plan Steps

**Problem:** When `approve_exploration()` merges a plan step's branch and encounters a conflict, it calls `sys.exit(1)`. In daemon mode, this kills the approval flow for that step and leaves it in "done" status forever. The daemon re-attempts every cycle, fails every cycle, and generates noise. For autonomous plan execution, merge conflicts are a permanent wedge.

Sequential plan steps rarely conflict (each depends on the previous, so they build on merged state). But they *can* conflict when: PROPOSAL.md exists on both branches (already handled by removal), or when two steps touch overlapping generated files (e.g., both update a central index file).

**Solution:** Plan steps get automatic conflict resolution with `-X theirs`:

1. First attempt: standard `git merge --no-ff`
2. On conflict: abort the merge, detect if this is a plan step
3. For plan steps: retry with `git merge --no-ff -X theirs` — the step's changes take precedence
4. If that also fails: fall through to the existing manual resolution path

`worktree.merge_branch()` gains a `strategy_option` parameter for this.

**Why `-X theirs` is safe for plan steps:** Each plan step runs in a worktree created from the latest main branch (with all previous steps merged). The step's changes are built on top of that state and passed verification. If there's a conflict, the step's version is more recent and was tested against the current codebase. The "ours" side (main) conflicts because an earlier step modified the same file — the later step's version supersedes it.

**Why not for standalone explorations:** Standalone explorations don't have the sequential dependency guarantee. Two independent explorations might legitimately conflict in ways that require human judgment.

### Daemon Plan Step Auto-Approve

**Problem:** When the daemon has `auto_approve=True`, it evaluates all "done" explorations that don't already have their own `auto_approve` flag set. But plan steps created by `execute_plan()` inherit `auto_approve` from the plan creation call. If a user runs `elmer implement "Milestone 1a"` without `--auto-approve`, plan steps get `auto_approve=False`. The daemon then skips them in `_refresh_running()` (which only auto-reviews explorations with `auto_approve=True`). The steps sit in "done" status, blocking the pipeline.

**Solution:** In the daemon's gate step (step 2), plan steps are always evaluated regardless of their per-exploration `auto_approve` flag. The logic: plan steps have verification commands as their quality gate. If verification passed and the step reached "done" status, the daemon should attempt AI review. Blocking on human review defeats the purpose of autonomous plan execution.

The `_refresh_running()` path (which fires on exploration completion) still respects the per-exploration flag — this change only affects the daemon's explicit gate sweep.

**Files modified:** `implement.py` (validate_plan function), `cli.py` (dry-run validation display), `gate.py` (merge conflict recovery with -X theirs), `worktree.py` (strategy_option parameter on merge_branch), `daemon.py` (plan step auto-approve in gate step).

## ADR-047: Parallel Conflict Detection and Daemon Auto-Retry for Plan Steps

**Decision:** Two improvements for autonomous plan execution reliability: pre-flight detection of file conflicts between parallel steps, and automatic retry of failed plan steps in daemon mode.

### Parallel Step Conflict Detection

**Problem:** When a plan declares steps that can run in parallel (no dependency chain between them), both steps might modify the same files. The merge of one step's branch could conflict with the other's. The `detect_parallel_conflicts()` analysis from ADR-046 checks archetype existence and DAG validity, but says nothing about whether parallel steps will produce merge conflicts at integration time.

`key_files` declarations in the plan JSON already document which files each step creates or modifies. Steps that could run concurrently (neither transitively depends on the other) with overlapping `key_files` are likely to conflict.

**Solution:** `detect_parallel_conflicts()` in `implement.py`:

1. Builds the transitive dependency closure for each step (BFS from `depends_on`)
2. Identifies all pairs of steps where neither is in the other's closure (parallel candidates)
3. Checks `key_files` overlap between each parallel pair
4. Returns warnings for pairs with shared files

Wired into `--dry-run` output after plan validation:
```
Parallel conflict warnings (1):
  ~ steps 2 and 4 may conflict: both declare key_files package.json
  (Use --max-concurrent=1 to avoid, or add depends_on to serialize)
```

**Why key_files and not static analysis:** Static analysis of `topic` text to predict which files a step will touch is unreliable and expensive. `key_files` is the decompose agent's explicit declaration — it already lists files that subsequent steps need to see. Overlap means both steps claim ownership of the same file.

**Why warnings, not errors:** Overlapping `key_files` is a heuristic. Two steps might both declare `package.json` but modify different sections. The warning gives the operator a signal; `--max-concurrent=1` or adding `depends_on` are the fixes.

### Daemon Auto-Retry for Failed Plan Steps

**Problem:** When a plan step fails (after exhausting verification amend retries), `_refresh_running()` pauses the plan and waits for human intervention. In daemon mode with `--auto-approve`, this defeats autonomous plan execution — a single step failure permanently blocks the pipeline until a human runs `elmer implement --resume`.

The failure-aware retry mechanism (ADR-045) already injects previous failure context into retry topics, making retries significantly more effective than blind re-runs. But this context is only used when a human triggers `elmer retry` or `elmer implement --resume`.

**Solution:** The daemon now auto-retries failed plan steps (Step 1.75 in the cycle) when `auto_approve` is enabled:

1. Scans for paused plans with failed steps
2. Filters to root-cause failures only (excludes cascade failures whose `proposal_summary` starts with `(dependency failed:`)
3. Skips steps that have already been retried (detected via `## Previous Attempt Failed` in the topic — injected by ADR-045's failure-aware retry)
4. Calls `gate.retry_exploration()` for each retriable step
5. Un-pauses the plan to "active" so the scheduler can proceed

**One retry, not infinite:** The `## Previous Attempt Failed` marker in the topic serves as the retry limit. First failure → automatic retry with failure context. Second failure (topic already has the marker) → plan stays paused for human review. This gives one shot at self-healing without risking a retry loop that burns budget.

**Why catch SystemExit:** `retry_exploration()` uses `sys.exit(1)` for error paths (exploration not found, wrong status). In daemon context, `SystemExit` would kill the daemon process. Catching it alongside `RuntimeError` keeps the daemon alive.

**Why only with auto_approve:** Auto-retry without auto-approve creates zombie retries — they complete, produce proposals, and sit in "done" status with nobody to review them. Tying auto-retry to `auto_approve` ensures the full pipeline (retry → review → approve → schedule next) operates autonomously.

**Files modified:** `implement.py` (detect_parallel_conflicts function), `cli.py` (parallel conflict warnings in dry-run), `daemon.py` (auto-retry for paused plans in daemon cycle step 1.75).

## ADR-048: Dependency Visibility and Cost Observability

**Decision:** Two observability improvements addressing operational blind spots in autonomous plan execution: pending exploration dependency display and cost parsing failure warnings.

### Pending Exploration Dependency Visibility

**Problem:** `elmer status` shows pending explorations with a "." icon but no indication of *why* they're pending. The operator sees 5 pending explorations and can't tell if they're waiting on running explorations (normal), on done explorations awaiting review (actionable), or on failed explorations (broken pipeline). The information exists in the `dependencies` table but isn't surfaced.

**Solution:** `show_status()` in `review.py` now queries dependencies for each pending exploration and displays unmet ones:

```
. build-user-service     pending    implement      opus     2h
      waiting on: setup-scaffold [running], create-db-schema [done]
```

Only unmet dependencies are shown (not already-approved ones). Missing dependencies (deleted from DB) show as `[missing]`, which flags a data integrity issue.

### Cost Parsing Failure Warnings

**Problem:** When a Claude session crashes or produces truncated JSON in its log file, `worker.parse_log_costs()` returns None. The exploration transitions to done/failed with `cost_usd=NULL` in the database. `SUM(cost_usd)` queries silently skip NULL values, so plan-level and cycle-level cost totals undercount. Over many plan steps, missing costs compound — a $50 plan might report $35 spent because 30% of sessions had truncated logs.

The cost data is genuinely lost (the API was called, money was spent), but the system doesn't even acknowledge the gap.

**Solution:** `_refresh_running()` now logs warnings when cost data is unavailable:

- `parse_log_costs()` returns None: `Warning: could not parse log for <id> (cost data missing)`
- `parse_log_costs()` returns a result but `cost_usd` is None: `Warning: no cost data in log for <id> (log may be truncated)`

In daemon mode, these warnings appear in `daemon.log`, giving operators a signal to investigate. The fix doesn't invent cost data — it makes the gap visible.

**Files modified:** `review.py` (dependency visibility in show_status, cost parsing warnings in _refresh_running).

*Revised: 2026-02-25, ADR-051 removed budget validation subsection*

---

## ADR-049: Retry Dependency Repair and Pre-Approval Plan Completion Check

Fixes two correctness/safety bugs in the plan lifecycle, both identified during Phase 7 pipeline audit and documented in ROADMAP.md Future Directions A1 and A2.

### Retry Dependency Management (A1)

**Problem:** When `gate.retry_exploration()` retries a failed plan step, `state.delete_exploration()` deletes the old exploration AND all its dependency records (both `exploration_id` and `depends_on_id` rows). Cascade-failed dependents remain in the database as `failed` with dangling dependency references. After a successful retry, these dependents need re-creation with correct dependencies pointing at the new exploration — but nothing rebuilds them.

Concrete scenario: Plan with steps 0→1→2. Step 0 fails. Steps 1 and 2 cascade-fail. Daemon retries step 0, creating "step-0-2". Step 0-2 succeeds. But step 1 is still failed with a dependency reference to the now-deleted "step-0". When `resume_plan()` or daemon auto-retry attempts to recover step 1, it calls `retry_exploration()` which creates a new exploration with NO dependency records — losing the plan's ordering guarantees.

**Solution:** `_rebuild_plan_dependencies()` in `gate.py` reconstructs the entire plan dependency graph from the plan JSON after any plan step retry:

1. Reads the plan JSON to get the canonical `depends_on` index lists
2. Maps step indices to current exploration IDs (which may differ from original due to retries)
3. Clears all stale dependency records for plan explorations
4. Rebuilds correct dependency records from the plan definition
5. Resets cascade-failed dependents (those with `proposal_summary` starting with "(dependency failed:") to `pending` status so they can be scheduled when dependencies are met

Called automatically from `retry_exploration()` when the retried exploration has a `plan_id`. Also called from `resume_plan()` for the case where only cascade failures exist (no root-cause failure to retry).

`resume_plan()` now separates root-cause failures from cascade failures, only retrying root-cause failures explicitly. Cascade-failed steps are handled by the dependency rebuild.

### Plan Completion Check Ordering (A2)

**Problem:** The plan-level `run_completion_check()` runs AFTER the last step is approved and merged to main (via `get_plan_status()` detecting `_newly_completed`). If integration verification fails, the broken code is already on the main branch. The check is supposed to catch integration issues, but it runs too late to prevent them.

**Solution:** The daemon's auto-approve loop (Step 2) now runs a pre-approval completion check before approving the last step of a plan:

1. `is_last_plan_step()` detects when approving an exploration would complete its plan (all other steps already approved)
2. `get_completion_verify_cmd()` resolves the verification command (extracted from `run_completion_check` for reuse)
3. If a completion command exists, it runs in the step's WORKTREE before approval — the worktree was branched after all prior steps were merged, so it represents the fully assembled state
4. If the check fails, the step is held as `done` for human review and the plan is paused
5. If the check passes (or no command is configured), auto-approval proceeds normally

The post-merge completion check in daemon Step 6c is retained as a fallback for plans that reach completion through non-daemon paths (e.g., manual `elmer approve`).

`run_completion_check()` gains a `cwd` parameter to support running in a worktree (pre-approval) vs project directory (post-merge).

### Schema Fix

The `plans` table CREATE TABLE statement was missing `completion_note` column — it was only added via ALTER TABLE migration that ran before the CREATE TABLE for fresh databases. Fixed by including it in the table definition. Existing databases are unaffected (ALTER TABLE migration still runs for backwards compatibility).

*Revised: 2026-02-25, ADR-051 removed budget_usd from plans schema*

**Files modified:** `gate.py` (`_rebuild_plan_dependencies`, wired into `retry_exploration`), `implement.py` (`get_completion_verify_cmd`, `is_last_plan_step`, `run_completion_check` cwd parameter, `resume_plan` root/cascade separation), `daemon.py` (pre-approval completion check in Step 2), `state.py` (plans table schema fix).

---

## ADR-050: Amend Failure Pattern Detection

**Problem:** When auto-amend retries all produce the same verification error output, the root cause is systemic (missing environment variable, broken dependency, incorrect test fixture) rather than a code bug the agent can fix. Each amend attempt costs money — a session runs, produces code changes, then verification fails with the exact same output. With `max_retries=2`, this wastes 2 full Claude sessions before failing.

Real-world example from srf-yogananda-teachings: a `validate` command failed because a required cross-reference target didn't exist. The amend agent restructured code each time, but the missing cross-reference was environmental. Three amend sessions ($4.50 total) produced three different code approaches, all failing identically.

**Solution:** `_is_repeated_failure()` in `review.py` compares the current verification failure output with the previous attempt's output. If the first 500 characters are identical (after whitespace normalization), the failure is classified as systemic and `_attempt_auto_amend()` returns False immediately — skipping the amend session.

Implementation:
- Verification output is stored in `.elmer/logs/{id}.verify` (one file per exploration)
- On first failure: stores output, returns False (no comparison available yet)
- On subsequent failures: compares with stored output. If identical, returns True (systemic)
- If different, updates stored output and returns False (new failure mode worth retrying)
- On verification success, the `.verify` file is deleted

The 500-character comparison window is a deliberate trade-off. Too short (< 100 chars) catches false positives from common error prefixes. Too long (full output) misses matches where only a timestamp or PID differs. 500 chars captures the error message and first few lines of stack trace — enough to identify the failure mode.

The check only fires when `amend_count > 1` — the first amend always proceeds because the initial failure might be a flaky test or timing issue. Repeated identical output is the signal that the problem is structural.

**Files modified:** `review.py` (`_is_repeated_failure`, called from `_attempt_auto_amend`, `.verify` file cleanup on success).

---

## ADR-051: Remove Budget Enforcement — Delegate to Claude CLI

**Decision:** Remove all dollar-budget enforcement from Elmer. Passive cost tracking (parsing `cost_usd` from session logs, recording in `costs` table, `elmer costs` command) is retained. Budget enforcement — `--budget` flags, plan-level budget caps, per-cycle daemon budget, budget validation warnings — is removed entirely.

**Problem:** Budget enforcement accumulated significant complexity across 4+ ADRs (043, 044, 047, 048) and threaded `budget_usd` parameters through every major code path: `explore.py`, `implement.py`, `daemon.py`, `worker.py`, `gate.py`, `state.py`, `cli.py`, `mcp_server.py`. This created cognitive overhead for both human readers and AI agents implementing new features. Every function that touched exploration creation or scheduling had to understand budget parameters, and budget edge cases (NULL coalescing, per-step allocation, plan-level circuit breakers) generated defensive code disproportionate to the value delivered.

Meanwhile, Claude CLI already enforces per-session budgets via `--max-budget-usd`. Elmer's budget enforcement was a second layer on top, with the only unique value being plan-level budget caps. In practice, plan-level budget rarely prevented real problems — it either wasn't set, or when set, the per-step allocation was too imprecise (even division across heterogeneous steps) to be useful.

**What was removed:**
- `--budget` CLI options from `explore`, `batch`, `implement`, `generate`, `amend`, `daemon`
- `budget_usd` parameter from `start_exploration()`, `start_ensemble()`, `launch_pending()`, `amend_exploration()`, `execute_plan()`, `run_daemon()`, `_run_cycle()`
- `--max-budget-usd` passthrough to `spawn_claude()` and `run_claude()`
- Plan-level budget enforcement in `schedule_ready()` (ADR-043)
- Daemon cycle budget check in `_run_cycle()` (Step 7)
- `budget_usd` column from `explorations` migration list and `plans` CREATE TABLE
- `get_plan_spend()` from `state.py` (dead code after enforcement removal)
- Budget validation warnings in `execute_plan()` (ADR-048)
- Budget display in `costs.py`, `show_plan_status()`, MCP tools
- Budget config comments from `config.toml` defaults

**What was retained:**
- `cost_usd` field in explorations (passive tracking)
- `costs` table for meta-operation cost tracking
- `elmer costs` command and `elmer_costs` MCP tool
- Cost parsing from session logs (`parse_log_costs`)
- Cost display in status, plan status, and logs
- Token count tracking (`input_tokens`, `output_tokens`)
- Cost rate configuration in `[costs.rates]`

**Why not keep budget as optional:** Optional budget that nobody uses is still code every contributor must understand. The parameter threading alone touched 20+ function signatures. Removing it entirely eliminates the cognitive tax. If budget enforcement is needed in the future, Claude CLI's `--max-budget-usd` can be set globally via environment or wrapper script — no Elmer code required.

**ADRs revised:** ADR-043 (removed plan budget enforcement subsection), ADR-048 (removed budget validation subsection).

**Files modified:** `cli.py`, `explore.py`, `implement.py`, `daemon.py`, `worker.py`, `gate.py`, `state.py`, `mcp_server.py`, `config.py`, `costs.py`.

---

## ADR-052: Decompose implement.py into decompose, plan, implement

**Decision:** Split the 985-line `implement.py` into three focused modules:

- **`decompose.py`** — Milestone decomposition: `_read_project_context()`, `_scan_filesystem()`, `_parse_plan_json()`, `decompose_milestone()`, `inject_answers()`, `load_plan()`, `validate_prerequisites()`, `validate_plan()`, `detect_parallel_conflicts()`.
- **`plan.py`** — Plan lifecycle: `get_plan_status()`, `show_plan_status()`, `resume_plan()`, `get_completion_verify_cmd()`, `is_last_plan_step()`, `run_completion_check()`.
- **`implement.py`** — Execution orchestration: `execute_plan()`, `_build_step_context()`.

**Why:** `implement.py` was doing three structurally different things — converting milestones to plans, executing plans as explorations, and tracking plan lifecycle. These have different dependencies, different change frequencies, and different callers. The daemon only needs `plan.py`. The CLI needs all three. The MCP server needs `decompose.py` + `implement.py` + `plan.py`.

**What changed:**
- `_inject_answers` renamed to `inject_answers` (public API in `decompose.py`, was already called externally from CLI).
- `validate_plan` signature changed from `(plan, elmer_dir)` to `(plan, project_dir)` — it validates agent definitions via `resolve_agent(project_dir, ...)` instead of `resolve_archetype(elmer_dir, ...)`.
- `daemon.py` imports `plan as plan_mod` instead of `implement as impl_mod` for lifecycle functions.
- Test imports updated: `from elmer.plan import ...` instead of `from elmer.implement import ...`.

**Files created:** `decompose.py`, `plan.py`.
**Files modified:** `implement.py`, `cli.py`, `mcp_server.py`, `daemon.py`, `tests/test_completion_check.py`.

---

## ADR-053: Remove Template Mode — Agent-Only Resolution

**Decision:** Remove the template-with-`$TOPIC`-substitution fallback from all archetype and meta-operation resolution. Agent definitions (ADR-026) are now the only invocation path.

**Why:** Agent mode (custom Claude Code subagents via `--agents`/`--agent` flags) is strictly superior to template mode. Template mode existed as a backward-compatibility fallback from before ADR-026. It complicated the resolution chain with a 4-step path (project `.claude/agents/` → bundled `agents/` → project `.elmer/archetypes/` → bundled `archetypes/`). Removing steps 3-4 simplifies every meta-operation module and eliminates the dual-code-path maintenance burden.

**Scope of change:**
- `explore.py`: `_resolve_agent_and_prompt()` raises `RuntimeError` if no agent found instead of falling back to template. `_assemble_prompt()` removed (dead code). `archetype_path` parameter removed from `_resolve_agent_and_prompt()`. Validation in `start_exploration()` uses `resolve_agent()` instead of `resolve_archetype()`.
- All meta-operation modules (`autoapprove.py`, `questions.py`, `insights.py`, `digest.py`, `generate.py`, `promptgen.py`, `archselect.py`, `invariants.py`): removed `else` branches with template fallback. Agent path code unchanged.
- `promptgen.py`: archetype hint now comes from `resolve_agent()` prompt field instead of template file.
- `archselect.py`: `list_exploration_archetypes()` reads from `AGENTS_DIR` instead of `ARCHETYPES_DIR`.
- `config.py`: `init_project()` no longer copies templates to `.elmer/archetypes/`.
- `cli.py` and `mcp_server.py`: archetype listing reads from `AGENTS_DIR` and `.claude/agents/elmer-*.md`.

**What was retained:**
- `resolve_archetype()` function in `config.py` — kept but no longer called by any operational code.
- `ARCHETYPES_DIR` constant — bundled template files remain in `src/elmer/archetypes/` as reference material but are not used for execution.
- All 28 agent definitions in `src/elmer/agents/` — these are the canonical source of archetype methodology.

**Migration for existing projects:** Projects with custom archetypes in `.elmer/archetypes/` must convert them to agent definitions in `.claude/agents/elmer-<name>.md` with YAML frontmatter.

**Files modified:** `explore.py`, `autoapprove.py`, `questions.py`, `insights.py`, `digest.py`, `generate.py`, `promptgen.py`, `archselect.py`, `invariants.py`, `config.py`, `cli.py`, `mcp_server.py`.

---

## ADR-054: Daemon Per-Cycle Approval Limits

**Decision:** Add `max_approvals_per_cycle` configuration (default: 10) to limit how many explorations the daemon auto-approves in a single cycle.

**Why:** For doc-only projects (like srf-yogananda-teachings), the existing auto-approve criteria "document-only proposals with no code changes" is tautologically true — every change is a document change. Without a per-cycle limit, the daemon running `--auto-approve --generate` could approve dozens of changes overnight without human checkpoint. The limit creates a natural pacing mechanism: after N approvals per cycle, remaining explorations queue for the next cycle. Combined with the 10-minute cycle interval, this gives humans time to spot-check.

**Implementation:** Counter `cycle_approvals` in `_run_cycle()` increments on each `autoapprove.evaluate()` success. When the counter reaches `max_approvals_per_cycle`, the loop breaks with a log message. Remaining `done` explorations are deferred to the next cycle.

**Configuration:** `[daemon] max_approvals_per_cycle = 10` in config.toml. Override per-project (srf sets 3).

**Files modified:** `daemon.py`, `config.py`.

---

## ADR-055: Tighten Auto-Approve Criteria for Doc-Only Projects

**Decision:** Replace generic "document-only proposals with no code changes" criteria with project-specific semantic criteria for srf-yogananda-teachings:

- Maintain cross-reference integrity across all 13 project documents
- Do not contradict existing ADRs
- Preserve identifier sequence consistency (ADR-NNN, DES-NNN, PRO-NNN)
- Do not introduce speculative content or ungrounded claims about the teachings
- Maximum 5 files changed (reduced from 10)

**Why:** The generic criteria was designed for code projects where "document-only" is a meaningful filter. For srf, every change is document-only. The criteria must instead evaluate *semantic quality* — whether the change maintains the project's architectural consistency and theological constraints.

**Impact:** The AI review gate now has meaningful criteria to evaluate against. Combined with `max_approvals_per_cycle = 3` (ADR-054), srf operates with conservative autonomous bounds appropriate for a sacred-text project.

**Files modified:** `srf-yogananda-teachings/.elmer/config.toml`.

---

## ADR-056: Document-Coherence Verification for Doc-Only Projects

**Decision:** Merge ROADMAP items D1 (configurable document coherence verification) and D2 (pre-code project support) into a single feature. Three changes:

1. `elmer validate` exits with code 1 on invariant failure (was always 0). New `--check` flag for read-only mode.
2. `is_doc_only_project()` detects projects without build-system files (no package.json, pyproject.toml, Makefile, etc.).
3. `run_completion_check()` auto-detects doc-only projects and runs document-coherence verification (via `invariants.run_coherence_check()`) as the plan completion check when no explicit verify_cmd is configured.

**Why:** `elmer implement` was designed for code projects with build/test/lint verification commands. Doc-only projects like srf-yogananda-teachings have no code to build — their "verification" is document coherence. Without this, `elmer implement` on srf would silently skip completion verification, merging potentially inconsistent documents.

The auto-detection approach (rather than a config flag) follows Elmer's principle of being "project-aware but not project-prescriptive." Projects with build systems use their existing verification. Projects without them get coherence verification automatically.

**Design:** Document coherence is a project-level property checked *after* all plan steps merge to main. This is the right granularity: individual step verification (per-exploration `verify_cmd`) checks each change in isolation, while completion verification checks the assembled whole. Per-step document coherence would be redundant with the auto-approve review gate and expensive (each check spawns a Claude session).

**Exit code semantics:** `elmer validate` now returns exit 1 when any invariant fails. This makes it usable as a `verify_cmd` or `on_done` command: `on_done = "elmer validate --check"`.

**Files modified:** `cli.py` (exit codes, --check flag), `invariants.py` (is_doc_only_project, run_coherence_check), `plan.py` (auto-coherence fallback in run_completion_check).

---

## ADR-057: NULL Cost Handling — Distinguish $0.00 from Missing Data

**Decision:** Fix Python truthiness conflation where `if cost:` treated `0.0` as falsy, silently dropping zero-cost entries from aggregations. Three code fixes, one SQL cleanup:

1. `dashboard.py`: `if cost:` changed to `if cost is not None:` — zero-cost explorations now counted in project dashboard totals.
2. `plan.py:get_plan_status()`: `if exp["cost_usd"]:` changed to `if exp["cost_usd"] is not None:` — zero-cost steps included in plan cost totals.
3. `plan.py:show_plan_status()`: `if plan.get("total_cost"):` changed to `if plan.get("total_cost") is not None:` — plans with $0.00 total now display their cost instead of hiding it.
4. `daemon.py:_get_cycle_cost()`: removed redundant `AND cost_usd IS NOT NULL` from SQL query that already uses `COALESCE(SUM(cost_usd), 0.0)`.

**Why:** SQLite `SUM()` ignores NULL values (correct behavior). The defensive Python `or 0.0` pattern in `costs.py` and `mcp_server.py` was correct but inconsistent with the `if cost:` pattern in `dashboard.py` and `plan.py`. The `if cost:` idiom is a common Python gotcha — it conflates "no data" (None) with "zero cost" ($0.00). With growing usage, zero-cost explorations (e.g., cached responses, free-tier operations) would silently disappear from cost reports.

**Files modified:** `dashboard.py`, `plan.py`, `daemon.py`.

---

## ADR-058: Stale Pending Exploration TTL with Auto-Cancel

**Decision:** Pending explorations that exceed a configurable TTL are automatically cancelled (marked `failed`) during `schedule_ready()`. Three changes:

1. `state.py`: new `get_stale_pending(conn, max_age_hours)` query — selects pending explorations older than the threshold using SQLite datetime arithmetic.
2. `explore.py:schedule_ready()`: before cascade-failure detection and ready-launching, checks for stale pending explorations and auto-cancels them with a descriptive `proposal_summary`. Plans containing stale steps are paused.
3. `config.py`: new `[session] pending_ttl_days = 7` config option (default: 7 days). Set to 0 to disable.

**Why:** Pending explorations with unresolvable dependencies (e.g., the dependency was declined but the cascade detection didn't fire, or a dependency was manually deleted) can accumulate indefinitely. They appear in `elmer status`, consume visual space in the dashboard, and create confusion about what's actually active. The session watchdog (ADR-045) handles stuck *running* sessions but has no equivalent for *pending* ones.

The 7-day default is conservative — most legitimate dependencies resolve within hours (daemon cycles). A pending exploration stuck for a week almost certainly has an unresolvable dependency chain.

**Integration point:** `schedule_ready()` is the natural home because it already handles pending→running and pending→failed transitions (cascade failures). Adding stale-pending cleanup maintains the single-responsibility pattern: all pending-state transitions happen in one function, called every daemon cycle.

**Files modified:** `state.py`, `explore.py`, `config.py`.

---

## ADR-059: Verification Failure Counter per Exploration

**Decision:** Add a `verification_failures` counter to the explorations table, incremented each time `_run_verification()` returns `passed=False` in `_refresh_running()`. Three changes:

1. `state.py`: new `verification_failures INTEGER DEFAULT 0` column (via schema migration) and `increment_verification_failures()` function following the same pattern as `increment_amend_count()`.
2. `review.py`: call `increment_verification_failures()` at both verification failure points — initial verification (after exploration completes) and re-verification (after amend completes). This runs before `_attempt_auto_amend()` so the counter reflects the total number of verification attempts, not just amend attempts.
3. `plan.py`: include `verification_failures` in step status data from `get_plan_status()`, display in `show_plan_status()` when non-zero, and include total verification failures in the plan summary line.

**Why:** `amend_count` tracks how many times an exploration was amended, but not how many verification failures occurred. An exploration can fail verification, get amended, pass on re-verification, then fail again on a different issue — `amend_count` would be 2 but the user has no visibility into the verification failure pattern. The counter answers: "How flaky is verification for this exploration/plan?"

**Semantic distinction:** `amend_count` = "how many times did we try to fix it?" `verification_failures` = "how many times did verification fail?" A high ratio of failures to amends suggests the verification command itself may be flaky, not the exploration code.

**Files modified:** `state.py`, `review.py`, `plan.py`.

---

## ADR-060: Verification Execution Time Tracking

**Decision:** Track cumulative verification execution time per exploration via a `verification_seconds REAL DEFAULT 0` column. Three changes:

1. `state.py`: new `verification_seconds` column via schema migration.
2. `review.py`: `_run_verification()` extended to return 4-tuple `(passed, returncode, output, elapsed_seconds)` using `time.monotonic()` timing. New `_accumulate_verification_seconds()` helper adds elapsed time to the exploration's running total via SQL `COALESCE(verification_seconds, 0) + ?`. Called at all 4 verification call sites (initial, fallback, post-amend, post-amend fallback).
3. `plan.py`: `verification_seconds` included in step status data from `get_plan_status()`.

**Why:** Expensive verification commands (full test suites, end-to-end tests) consume wall-clock time that doesn't appear in token costs. Without timing data, operators can't distinguish between "exploration took 2 hours because it was complex" and "exploration took 2 hours because verification ran 8 times at 15 minutes each." The data enables budget forecasting when verification is the bottleneck.

**Accumulation pattern:** Unlike `verification_failures` (increment by 1), verification time accumulates fractional seconds. Each verification run adds its elapsed time to the total. This captures the full time cost including retries, fallbacks, and timeouts.

**Files modified:** `state.py`, `review.py`, `plan.py`.

---

## ADR-061: Plan Step Duration Estimation

**Decision:** Support optional `estimated_seconds` fields in plan step JSON for runtime forecasting. Three changes:

1. `decompose.py`: new `estimate_plan_duration(plan)` function — sums `estimated_seconds` from all steps, validates types, warns on partial/invalid estimates. Returns `(total_seconds, warnings)`.
2. `implement.py:execute_plan()`: after prerequisite validation, calls `estimate_plan_duration()` and displays estimated runtime. If `max_plan_hours` is configured and the estimate exceeds it, emits a warning.
3. `plan.py:show_plan_status()`: parses `estimated_seconds` from plan JSON and includes total estimated runtime and actual verification time in the progress summary line.
4. `config.py`: new `max_plan_hours` option under `[implement]` (commented out by default — advisory, not blocking).

**Why:** Plan steps can take anywhere from minutes (simple doc edits) to hours (complex multi-file implementations with verification). Without duration estimates, operators can't predict whether a plan fits within their available time window (e.g., overnight batch, weekend run). The decompose agent already has context to make rough estimates based on step complexity.

**Design choice:** `estimated_seconds` lives in the plan JSON (produced by the decompose agent), not as a DB column. This keeps the estimate with the plan definition rather than requiring schema changes per exploration. The `max_plan_hours` check is advisory (warning, not blocking) because estimates are inherently imprecise.

**Files modified:** `decompose.py`, `implement.py`, `plan.py`, `config.py`.

## ADR-062: Daemon Stuck State Prevention and Partial Plan Rollback

**Decision:** Fix two stuck-state bugs in autonomous operation:

1. **Paused plan auto-retry infinite loop** (daemon.py): When all `gate.retry_exploration()` calls throw exceptions, the plan stays paused and the daemon re-attempts the same retries every cycle. Fix: when all retries fail with exceptions, inject the "## Previous Attempt Failed" marker into the exploration topic so the retry-eligibility filter skips them next cycle. Logs a clear warning.

2. **Partial plan execution** (implement.py): When a step creation throws mid-plan, the plan stays "active" with gaps. Fix: track creation errors and pause the plan if any steps failed. If all steps fail, mark the plan as "failed" entirely. Provide guidance for retrying specific steps with `--steps`.

**Why:** Both bugs create infinite cycles of wasted work in autonomous operation. The daemon retries forever without progress, and partial plans schedule dependents that can never complete.

**Files modified:** `daemon.py`, `implement.py`.

## ADR-063: FIFO Approval Ordering and Normalized Failure Detection

**Decision:** Two quality improvements for autonomous operation:

1. **FIFO approval queue** (daemon.py): Sort done explorations by `completed_at` before processing the approval queue. Older explorations are approved first, preventing starvation when newer explorations flood the queue. Previously arbitrary iteration order.

2. **Normalized verification failure comparison** (review.py): The `_is_repeated_failure()` comparison (ADR-050) now strips timestamps, PIDs, temp paths, and hex addresses before comparing verification output. New `_normalize_verification_output()` function uses regex substitution to replace volatile tokens with placeholders (`<TS>`, `<PID>`, `<TMP>`, `<ADDR>`). This reduces false negatives where identical systemic failures produce slightly different output.

**Why:** FIFO ordering ensures fairness in approval batching. Normalized comparison prevents wasted amend cycles on systemic failures that only differ by timestamp or PID.

**Files modified:** `daemon.py`, `review.py`.

## ADR-064: Custom Skills as Verification Hooks (F3)

**Decision:** Project-defined Claude Code skills can be invoked as lifecycle hooks at three points:

- `on_done`: after PROPOSAL.md is committed, before verification. Failing hooks trigger auto-amend.
- `pre_approve`: in the daemon auto-approve gate, before AI review. Failing hooks block approval.
- `post_approve`: after merge. Informational only, cannot block.

Configuration in `[hooks]` section of config.toml:
```toml
[hooks]
on_done = ["mission-align"]
pre_approve = ["cultural-lens"]
model = "sonnet"
max_turns = 10
```

Implementation: New `hooks.py` module with `run_skill_hook()` and `run_event_hooks()`. Skills are loaded via `config.resolve_skill()` which reads `.claude/skills/<name>/SKILL.md`. The skill body is used as context alongside the proposal text. Skills must output a `VERDICT: PASS/FAIL` line; no verdict defaults to pass (informational).

New config functions: `resolve_skill()`, `list_project_skills()`, `get_hook_skills()`.

**Why:** srf-yogananda-teachings has 6 custom skills (`/mission-align`, `/cultural-lens`, `/seeker-ux`, `/dedup-proposals`, `/proposal-merge`, `/theme-integrate`). These encode project-specific quality criteria that the generic auto-approve gate cannot evaluate. Skill hooks let projects define semantic quality checks without modifying Elmer core.

**Files modified:** `hooks.py` (new), `config.py`, `review.py`, `daemon.py`.

## ADR-065: External Dependency Tracking with Blockers (D4)

**Decision:** Add external blocker management for tracking stakeholder decisions and prerequisites that gate implementation.

Schema: New `external_blockers` table with `id`, `description`, `status` (blocked/resolved), `created_at`, `resolved_at`. New `blocked_by` column on `explorations` table (comma-separated blocker IDs).

CLI commands: `elmer block <id> <description>`, `elmer unblock <id>`, `elmer blockers`.

Scheduling: `schedule_ready()` checks `blocked_by` against `external_blockers` — explorations with any unresolved blocker stay pending. Status display shows `blocked by: <ids>` for pending explorations.

Plan integration: Plan steps can include `blocked_by` in their definition. The decompose agent can reference external blockers when a step depends on an out-of-band decision.

**Why:** srf-yogananda-teachings has 15+ stakeholder decisions blocking implementation (SRF copyright stance, editorial voice, Neon account setup, Contentful configuration). Without external blocker tracking, the daemon either blocks indefinitely on unresolvable dependencies or requires manual workarounds.

**Files modified:** `state.py`, `explore.py`, `cli.py`.

## ADR-066: Stale PID Recovery and Cascade Failure Alerting

**Decision:** Two daemon resilience improvements:

1. **Stale PID recovery** (daemon.py): The pidfile now stores `PID TIMESTAMP`. On read, validates that the process owning the PID started after the pidfile was written (using `/proc/<pid>/stat` on Linux). If the PID was recycled (process started before pidfile timestamp), the pidfile is treated as stale and removed. Falls back to basic PID check on non-Linux systems.

2. **Cascade failure alerting** (explore.py): `schedule_ready()` now logs `CASCADE FAIL` and `CASCADE PAUSE` warnings when dependency failures propagate. Previously, cascade failures were silently applied with no operator notification. The `elmer.cascade` logger provides a dedicated channel for monitoring cascade events.

**Why:** PID recycling can lock out the daemon on restart, requiring manual `.elmer/daemon.pid` deletion. Cascade failures can silently fail an entire plan without alerting the operator, defeating autonomous operation.

**Files modified:** `daemon.py`, `explore.py`.
