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

**A3. Plan revision / replanning** (Large, architecture)
When a step failure reveals the plan is wrong (not just the implementation), allow mid-execution replanning. Requires: new meta-agent for plan revision, mapping existing step completions to revised plan, handling in-flight step cancellation, state management for plan transitions. Deferred from Phase 7 as too complex for incremental delivery.

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

---

## Deferred / Uncertain

See Open Questions in CONTEXT.md. Features discussed but not committed are tracked there.

*Last updated: 2026-02-25, F3 (ADR-064) + D4 (ADR-065) resolved, daemon resilience ADR-062/063/066, 7 remaining future directions*
