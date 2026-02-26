# Elmer — Roadmap

Seven phases complete. Git history has the full delivery record.

## Phase 1: Core Loop — COMPLETE

Manual explore → review → approve/decline. CLI primitives, git worktree isolation, SQLite state, three archetypes. Proved the loop is useful on a real project.

## Phase 2: Intelligence — COMPLETE

AI topic generation, DAG dependencies, auto-approve gate, two-stage prompt generation, cost controls, archetype evolution (8 exploration archetypes + AI selection).

## Phase 3: Autonomy — COMPLETE

Daemon loop, conditional chain actions, follow-up generation, cross-project insight log, question mining. Overnight autonomous operation.

## Phase 4: Meta — COMPLETE

Project scaffolding, template evolution stats, attention routing, document invariant enforcement, multi-project dashboard, PR-based review, batch topic lists, skill scaffolding.

## Phase 5: Integration — COMPLETE

MCP server exposing full Elmer functionality as structured tools (ADR-024). 18 tools over stdio JSON-RPC: 6 read-only (status, review with prioritization, costs, tree, archetypes, insights) + 8 mutation (explore, approve with bulk/followup/invariants, amend, decline, cancel, retry, clean, pr) + 3 intelligence (generate, validate, mine-questions) + 1 batch. Custom subagent integration converting all archetypes and meta-operations to Claude Code subagents with tool restrictions and model selection (ADR-026). Proposal amendment workflow (`elmer amend`, ADR-028).

## Phase 6: Convergence — COMPLETE

Decline reasons (`elmer decline ID "reason"`), convergence digests (`elmer digest`), digest-aware topic generation, daemon synthesis step with threshold trigger (ADR-030). Closes the feedback loop: explorations accumulate understanding, not just output. 21 MCP tools (added `elmer_digest`, `elmer_config_get`, `elmer_recover_partial`; preview/dry-run modes on `elmer_clean`, `elmer_validate`, `elmer_amend`; progress indicators on `elmer_status`; stagger on `elmer_batch`; digest metadata on `elmer_generate`). Daemon loop gains a two-timescale architecture: fast loop (explore → approve) and slow loop (digest → generate → explore).

Ensemble exploration (ADR-031): `--replicas N` on `explore` and `batch` runs the same topic N times with independent sessions, then auto-synthesizes into a single consolidated proposal. Archetype rotation (`--archetypes`) and model rotation (`--models`) maximize variance. Approval/decline cascades: approving synthesis cleans up replicas, declining synthesis declines all. New `synthesize.py` module, `elmer-meta-synthesize` agent, daemon integration. Two-scale convergence: ensemble (intra-topic) and digest (inter-topic).

## Phase 7: Implementation Engine — COMPLETE

Milestone decomposition and autonomous multi-step implementation (`elmer implement`). AI decomposes a high-level milestone into ordered plan steps with dependency tracking, then executes each step as a separate exploration with cross-step context. 11 ADRs (ADR-038 through ADR-048) across four iteration waves.

**Wave 1 — Foundation (ADR-038, 039):** Pre-merge verification hooks with auto-amend retry. Milestone decomposition via `elmer-meta-decompose` agent producing ordered JSON plans with `key_files`, `depends_on`, `verify_cmd`. Plan execution with dependency scheduling and cascade failure propagation.

**Wave 2 — Intelligence (ADR-040, 041, 042):** Cross-step context injection (approved predecessors' summaries feed into dependent step prompts). Plan loading from files. Fallback verification (build/test/lint auto-detection). Dependency cascade failures. Proposal structural validation. Prerequisites and artifact flow between steps. Greenfield decomposition for projects with no existing code.

**Wave 3 — Safety & Operations (ADR-043, 044, 045, 046):** Verify-cmd visibility in proposals. Amend cost attribution. Context budget management. Plan completion verification. Worktree setup commands. Session watchdog with TTL-based termination. Failure-aware retry (injecting failure context into retry prompts). Per-step model routing. Plan validation (structural + semantic checks). Merge conflict recovery with strategy escalation. Daemon auto-approve for completed plan steps.

**Wave 4 — Resilience & Observability (ADR-047, 048):** Parallel conflict detection (key_files overlap analysis for concurrent steps). Daemon auto-retry for failed plan steps with retry-limit detection. Pending dependency visibility in status display. Cost parsing failure logging.

---

## Future Directions

Organized by theme, grounded in both internal pipeline audit and real-world usage on a documentation-heavy pre-implementation project (srf-yogananda-teachings: 13 documents, 124 ADRs, 1.5 MB of architecture, zero code).

### A. Plan Lifecycle — Correctness & Recovery

**A1. Retry dependency management** — RESOLVED (ADR-049)
`_rebuild_plan_dependencies()` reconstructs the plan dependency graph from plan JSON after any step retry. Cascade-failed dependents are reset to pending. `resume_plan()` separates root-cause from cascade failures.

**A2. Plan completion check ordering** — RESOLVED (ADR-049)
Daemon pre-approval completion check runs in the last step's worktree before approving. `is_last_plan_step()` detects the last step; `get_completion_verify_cmd()` resolves the command. Post-merge check retained as fallback.

**A3. Plan revision / replanning** — RESOLVED (ADR-067)
`elmer replan <plan-id>` invokes a `replan` meta-agent that produces a revised plan preserving approved steps. `apply_revision()` remaps explorations, cancels dropped steps, creates new steps, rebuilds dependencies. Schema tracks `prior_plan_json`, `revision_count`, `replan_trigger_step`. Daemon auto-replan via `implement.auto_replan` config. MCP tool `elmer_replan` for Claude Code integration. Context injection includes revision note.

**A4. Exploration-to-plan pipeline** (Medium)
An approved exploration's PROPOSAL.md often contains the exact action items, file targets, and ordering needed for an implementation plan. `elmer implement --from-exploration ID` feeds the proposal directly to the decompose agent as structured context, eliminating the lossy manual translation from analysis to milestone description. The decompose agent receives both the milestone text and the full proposal, producing higher-fidelity plans that inherit the exploration's analysis.

### B. Execution Intelligence

**B1. Amend failure pattern detection** — RESOLVED (ADR-050)
`_is_repeated_failure()` compares verification output with previous attempt's stored output. Identical output (first 500 chars) triggers fail-fast, skipping the amend session. Stored in `.elmer/logs/{id}.verify`, cleaned on success.

**B2. Graceful session checkpoint** (Large)
Instead of hard-killing sessions that exceed TTL via `worker.terminate()`, implement a checkpoint mechanism. Save partial work before termination so it can be resumed rather than restarted from scratch.

**B3. Per-step model routing from project context** (Medium)
ADR-045 added per-step `model` field in plans. Currently set by the decompose agent based on step complexity. Could be informed by project-level model tiering policies (e.g., srf project defines Tier 1/2/3 model classifications in its CLAUDE.md).

### C. Observability & Cost

**C1. Verification failure tracking** — RESOLVED (ADR-059)
`verification_failures` counter on explorations table. Incremented at both verification failure points in `_refresh_running()`. Surfaced in `show_plan_status()` per-step and in summary line.

**C2. Verification execution time tracking** — RESOLVED (ADR-060)
`verification_seconds` column on explorations table. `_run_verification()` returns elapsed time via `time.monotonic()`. Accumulated at all 4 call sites (initial, fallback, post-amend, post-amend fallback). Surfaced in plan status.

**C3. NULL cost handling in SUM queries** — RESOLVED (ADR-057)
Fixed Python truthiness conflation (`if cost:` → `if cost is not None:`) in `dashboard.py`, `plan.py`. Removed redundant SQL `IS NOT NULL` filter in `daemon.py`. Zero-cost entries now correctly distinguished from missing data.

**C4. Daemon observability dashboard** (Medium)
Persistent status view (curses or web) showing real-time daemon cycle progress, plan status, cost tracking, and alerts. Currently all info requires running `elmer status` or reading daemon.log.

### D. Document-Heavy Projects (from srf-yogananda-teachings analysis)

**D1. Configurable document coherence verification** — RESOLVED (ADR-056)
`elmer validate` gains `--check` flag (read-only mode) and proper exit codes (exit 1 on failure). Custom invariant rules already supported via `[invariants] rules = [...]` in config.toml. Exit codes make `validate` usable as a `verify_cmd` or `on_done` command.

**D2. Pre-code project support** — RESOLVED (ADR-056)
`is_doc_only_project()` auto-detects projects without build-system files. `run_completion_check()` automatically runs document-coherence verification (via `invariants.run_coherence_check()`) as the plan completion check for doc-only projects. No configuration needed — projects with build systems use code verification, projects without get coherence verification.

**D3. Multi-document transactional updates** (Medium)
Proposal graduation in srf (PRO-NNN → ADR/DES) requires coordinated updates to 4+ documents. If any update fails or creates inconsistency, the whole graduation should roll back. Currently, Elmer explorations touch files independently. A "transactional exploration" mode could bundle related document changes with pre-merge invariant validation.

**D4. External dependency tracking** — RESOLVED (ADR-065)
New `external_blockers` table and `blocked_by` column on explorations. CLI commands: `elmer block`, `elmer unblock`, `elmer blockers`. Explorations referencing unresolved blockers stay pending. Status display shows `blocked by:` for pending explorations.

**D5. Arc/milestone orchestration** (Large)
srf has 7 arcs and 15 milestones forming a multi-month delivery structure. Elmer's `implement` handles single plans but not hierarchical plan composition. A "plan of plans" or milestone grouping would let Elmer orchestrate arc-level delivery with per-milestone plans.

### E. Content & Data Pipelines

**E1. Non-code exploration types** (Medium)
Current explorations assume code output on a branch. Data pipeline orchestration (PDF ingestion, embedding generation, search quality evaluation) produces data artifacts, not code. Elmer could support exploration "types" where the output isn't a PROPOSAL.md but a quality report, evaluation matrix, or data validation summary.

**E2. Parameter tuning explorations** (Medium)
srf needs systematic A/B testing of chunk sizes, RRF weights, cache TTLs. A specialized archetype or exploration mode that varies parameters, measures against a golden set, and produces a recommendation report. The ensemble mechanism (ADR-031 replicas with archetype rotation) is a natural fit — each replica uses a different parameter configuration.

**E3. Ensemble synthesis failure recovery** (Medium)
When synthesis fails (API outage), no mechanism to re-trigger. Add automatic re-queue or explicit "re-synthesize ensemble" command in daemon.

### F. Operational

**F1. Stale pending exploration cleanup** — RESOLVED (ADR-058)
`schedule_ready()` auto-cancels pending explorations older than `[session] pending_ttl_days` (default: 7). New `get_stale_pending()` SQL query. Plans containing stale steps are paused.

**F2. Plan step duration estimation** — RESOLVED (ADR-061)
`estimate_plan_duration()` sums `estimated_seconds` from plan JSON. Warns on partial/invalid estimates. `max_plan_hours` config option (advisory). Plan status shows estimated vs actual verification time.

**F3. Custom skills as verification hooks** — RESOLVED (ADR-064)
New `hooks.py` module invokes project-defined Claude Code skills at lifecycle points (`on_done`, `pre_approve`, `post_approve`). Skills loaded from `.claude/skills/<name>/SKILL.md`. Configured in `[hooks]` config section. Skills must output `VERDICT: PASS/FAIL` to gate transitions.

### G. Worker Intelligence

Context enrichment for AI workers running inside explorations. Workers currently start with near-zero knowledge of the broader system's accumulated intelligence — digests, decline history, sibling explorations. These items feed system knowledge into worker prompts.

**G1. Digest injection into exploration prompts** (Small)
Inject the latest convergence digest (truncated, ~4K chars) into individual exploration worker prompts, not just topic generation. Workers currently re-discover insights that the digest already synthesizes. Add a `## Recent Project Digest` section in `explore.py`'s prompt assembly, parallel to the existing cross-project insights injection. Config: `[digest] inject_into_explorations = true`. Resolves the open question about injecting digest context into exploration prompts (CONTEXT.md).

**G2. Sibling-aware exploration prompts** (Small)
Inject a brief summary of other in-flight explorations (one line per sibling: topic + archetype) into the worker prompt. Prevents parallel explorations from duplicating analysis or proposing conflicting changes. Query `state.list_explorations()` for running/pending status, append as a note section. ~20 lines in `explore.py`. Partially addresses the sibling-awareness open question in CONTEXT.md.

**G3. Decline-reason injection for related topics** (Medium)
When an exploration's topic keywords match previously declined topics, inject those decline reasons into the worker prompt: `## Prior Declined Approaches` with topic and reason per entry. Capped at 3 entries, 500 chars total. Uses existing archive metadata reading from `digest.py`. The decline reason is the most concentrated learning signal in Elmer — currently it feeds only digests and generation, but the worker who most needs it never sees it.

**G4. Mid-exploration questions protocol** (Large)
A protocol for the worker to signal "I need input" during exploration. Worker writes `QUESTIONS.md` (structured: numbered questions with context) to the worktree, then finishes its session. New state: `waiting`. `elmer status` surfaces waiting explorations prominently. New command: `elmer answer ID` provides responses. System resumes with a new session in the same worktree, injecting questions + answers. MCP tool: `elmer_answer`. Agent methodology teaches the protocol. Distinct from B2 (crash checkpointing): B2 saves involuntary partial work before TTL-kill; G4 is intentional interactive pause for human input. ~300 lines across state.py, cli.py, explore.py, mcp_server.py.

### H. Proposal Quality & Review

Standardize proposal output and review signals to make proposals machine-parseable and reviewer-friendly.

**H1. Confidence annotations in proposals** (Small)
Teach agents to mark uncertainty levels per section: `[HIGH CONFIDENCE]`, `[UNCERTAIN — depends on X]`, `[SPECULATIVE]`. Forces explicit reasoning about knowledge vs. assumptions during exploration. The coordinator and auto-approve gate can prioritize review attention on uncertain sections. Agent methodology change in `src/elmer/agents/*.md` — no engine work required.

**H2. Structured PROPOSAL.md schema** (Medium)
Standardize PROPOSAL.md with YAML frontmatter (`type`, `confidence`, `key_files`, `decision_needed`) and conventional sections (Summary, Analysis, Recommendations, Open Questions). Makes proposals machine-parseable. Enables: smarter `--prioritize` ranking, automated conflict detection between proposals, richer MCP tool responses. Requires agent definition updates and optional frontmatter extraction in `review.py`.

**H3. AI-authored review notes** (Small)
Workers write a companion `REVIEW-NOTES.md` alongside PROPOSAL.md containing: sections of highest uncertainty, assumptions made, questions for the reviewer, what would change with more turns. Creates an honest meta-channel — the worker often "knows" where its proposal is weak but currently has no way to communicate this. Agent methodology change plus optional display in `elmer review ID`.

### I. Agent Evolution

Close the feedback loop between exploration outcomes and agent methodology.

**I1. Archetype effectiveness diagnosis** (Medium)
`elmer archetypes diagnose <name>` reads approval/decline rates, decline reasons, and verification failure counts for a given archetype. Produces a structured report: what topics succeed, what topics fail, common decline reasons, average turns used. Read-only — no automatic modifications. Uses existing `archstats.py` data plus archive metadata. Prerequisite for I2.

**I2. Agent methodology self-improvement** (Large)
After I1 provides diagnosis, a meta-agent generates revised agent prompt text based on observed failure patterns. `elmer archetypes refine <name>` produces a diff of the proposed changes for human review. Never automatic — human approves prompt changes. Requires I1 as prerequisite and a new meta-agent definition.

### J. Agent Teams Integration

Agent Teams (experimental Claude Code feature) enable multiple Claude Code instances to coordinate within a session via shared task lists and inter-agent messaging. Currently rejected for core Elmer operations because they're session-scoped and don't persist (CLAUDE.md constraint). However, specific use cases could benefit from intra-session parallelism with real-time debate between agents.

**J1. Ensemble exploration via Agent Teams** (Medium)
Replace the current ensemble mechanism (N separate `claude -p` sessions + post-hoc synthesis agent) with a single Agent Team where teammates explore from different archetype lenses and debate in real-time. The lead synthesizes findings naturally through inter-agent challenge rather than reading N completed proposals after the fact. Quality improvement: teammates can challenge each other's reasoning and build on findings, producing synthesis that's strictly better than post-hoc assembly. Requires J3 as prerequisite.

**J2. Collaborative decomposition** (Medium)
For `elmer implement`, the decompose meta-agent runs alone. A team-based decomposition spawns teammates to analyze different aspects of the codebase (dependency structure, test coverage, existing patterns) and debate the step ordering before the lead produces the final plan. Higher-quality plans at higher token cost. Appropriate for large milestones where decomposition quality is the bottleneck. Requires J3 as prerequisite.

**J3. Headless Agent Teams feasibility** (Small — research)
The blocking question for J1 and J2: can `claude -p` (print mode) create and coordinate Agent Teams? The docs describe interactive usage with tmux/iTerm2 split panes and `Shift+Down` cycling. Test whether team coordination works in headless mode. If not, the integration path narrows to a new "interactive exploration" mode that accepts the session-scoped constraint for higher-quality results. Key test: run `claude -p` with a prompt that requests an agent team and observe whether teammates spawn and coordinate.

**J4. Inter-exploration messaging** (Large)
The most ambitious Agent Teams integration: concurrent Elmer explorations on the same project could form an ad-hoc team, sharing findings via the mailbox system. Exploration A discovers a critical constraint; Exploration B receives it before committing to an incompatible approach. This transforms parallel explorations from independent to collaborative. Major architectural tension: Agent Teams are session-scoped, Elmer explorations are persistent. Would require either (a) wrapping the team in a persistent Elmer layer that survives session death, or (b) accepting that collaborative explorations are ephemeral but higher-quality. Depends on J3 feasibility results.

---

## Deferred / Uncertain

See Open Questions in CONTEXT.md. Features discussed but not committed are tracked there.

*Last updated: 2026-02-25, added G (worker intelligence), H (proposal quality), I (agent evolution), J (Agent Teams), A4 (exploration-to-plan); 22 remaining future directions*
