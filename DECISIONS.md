# Elmer — Decisions

Architecture Decision Records. Mutable living documents — update directly when decisions evolve. When substantially revising an ADR, add `*Revised: [date], [reason]*` at the section's end. Git history serves as the full audit trail.

24 ADRs recorded.

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

4. **Execute.** Each step becomes a chained exploration (`elmer explore` with `--verify-cmd`, `depends_on`, `plan_id`, `plan_step`). Steps execute in dependency order — each waits for its dependencies to be approved and merged before starting. Chain mode (sequential by default, `--max-concurrent` for parallelism within dependency constraints). Auto-approve is on by default for implementation plans. Budget is divided evenly across steps when `--budget` is set.

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

**Solution:** Two refinements:

1. **Diff size guard** — even with passing verification, check the number of files changed against `max_files_changed` (from `[auto_approve]` config, default 10). Small diff + passing tests = safe to shortcut. Large diff + passing tests = fall through to AI review, because broad changes need architectural review even if they compile.

2. **Configurable shortcut** — new config option `[verification] auto_approve_on_pass` (default: `true`). Set to `false` to require AI review for all explorations regardless of verification status. Useful for projects where architectural discipline matters more than throughput.

```toml
[verification]
on_done = "npm test && npm run lint"
auto_approve_on_pass = true    # false = always require AI review

[auto_approve]
max_files_changed = 10         # diff size guard for verification shortcut
```

**Files modified:** `state.py` (get_pending_blocked query), `explore.py` (cascade in schedule_ready), `autoapprove.py` (structural validation, verification guard).
