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

**A1.** Retry dependency management — RESOLVED (ADR-049)
**A2.** Plan completion check ordering — RESOLVED (ADR-049)
**A3.** Plan revision / replanning — RESOLVED (ADR-067)
**A4.** Exploration-to-plan pipeline — RESOLVED (ADR-068)

### B. Execution Intelligence

**B1.** Amend failure pattern detection — RESOLVED (ADR-050)

**B2. Graceful session checkpoint** (Large)
Instead of hard-killing sessions that exceed TTL via `worker.terminate()`, implement a checkpoint mechanism. Save partial work before termination so it can be resumed rather than restarted from scratch.

**B3.** Per-step model routing from project context — RESOLVED (ADR-069)

### C. Observability & Cost

**C1.** Verification failure tracking — RESOLVED (ADR-059)
**C2.** Verification execution time tracking — RESOLVED (ADR-060)
**C3.** NULL cost handling in SUM queries — RESOLVED (ADR-057)

**C4. Daemon observability dashboard** (Medium)
Persistent status view (curses or web) showing real-time daemon cycle progress, plan status, cost tracking, and alerts. Currently all info requires running `elmer status` or reading daemon.log.

### D. Document-Heavy Projects (from srf-yogananda-teachings analysis)

**D1.** Configurable document coherence verification — RESOLVED (ADR-056)
**D2.** Pre-code project support — RESOLVED (ADR-056)

**D3. Multi-document transactional updates** (Medium)
Proposal graduation in srf (PRO-NNN → ADR/DES) requires coordinated updates to 4+ documents. If any update fails or creates inconsistency, the whole graduation should roll back. Currently, Elmer explorations touch files independently. A "transactional exploration" mode could bundle related document changes with pre-merge invariant validation.

**D4.** External dependency tracking — RESOLVED (ADR-065)

**D5. Arc/milestone orchestration** (Large)
srf has 7 arcs and 15 milestones forming a multi-month delivery structure. Elmer's `implement` handles single plans but not hierarchical plan composition. A "plan of plans" or milestone grouping would let Elmer orchestrate arc-level delivery with per-milestone plans.

### E. Content & Data Pipelines

**E1. Non-code exploration types** (Medium)
Current explorations assume code output on a branch. Data pipeline orchestration (PDF ingestion, embedding generation, search quality evaluation) produces data artifacts, not code. Elmer could support exploration "types" where the output isn't a PROPOSAL.md but a quality report, evaluation matrix, or data validation summary.

**E2. Parameter tuning explorations** (Medium)
srf needs systematic A/B testing of chunk sizes, RRF weights, cache TTLs. A specialized archetype or exploration mode that varies parameters, measures against a golden set, and produces a recommendation report. The ensemble mechanism (ADR-031 replicas with archetype rotation) is a natural fit — each replica uses a different parameter configuration.

**E3.** Ensemble synthesis failure recovery — RESOLVED (ADR-070)

### F. Operational

**F1.** Stale pending exploration cleanup — RESOLVED (ADR-058)
**F2.** Plan step duration estimation — RESOLVED (ADR-061)
**F3.** Custom skills as verification hooks — RESOLVED (ADR-064)

### G. Worker Intelligence

**G1.** Digest injection into exploration prompts — RESOLVED (ADR-071)
**G2.** Sibling-aware exploration prompts — RESOLVED (ADR-071)
**G3.** Decline-reason injection for related topics — RESOLVED (ADR-071)

**G4. Mid-exploration questions protocol** (Large)
A protocol for the worker to signal "I need input" during exploration. Worker writes `QUESTIONS.md` (structured: numbered questions with context) to the worktree, then finishes its session. New state: `waiting`. `elmer status` surfaces waiting explorations prominently. New command: `elmer answer ID` provides responses. System resumes with a new session in the same worktree, injecting questions + answers. MCP tool: `elmer_answer`. Agent methodology teaches the protocol. Distinct from B2 (crash checkpointing): B2 saves involuntary partial work before TTL-kill; G4 is intentional interactive pause for human input. ~300 lines across state.py, cli.py, explore.py, mcp_server.py.

### H. Proposal Quality & Review

**H1.** Confidence annotations in proposals — RESOLVED (ADR-072)
**H2.** Structured PROPOSAL.md schema — RESOLVED (ADR-072)
**H3.** AI-authored review notes — RESOLVED (ADR-072)

### I. Agent Evolution

**I1.** Archetype effectiveness diagnosis — RESOLVED (ADR-073)

**I2. Agent methodology self-improvement** (Large)
After I1 provides diagnosis, a meta-agent generates revised agent prompt text based on observed failure patterns. `elmer archetypes refine <name>` produces a diff of the proposed changes for human review. Never automatic — human approves prompt changes. Requires I1 as prerequisite and a new meta-agent definition.

### J. Agent Teams Integration

Agent Teams (experimental Claude Code feature) enable multiple Claude Code instances to coordinate within a session via shared task lists and inter-agent messaging. Currently rejected for core Elmer operations because they're session-scoped and don't persist (CLAUDE.md constraint). However, specific use cases could benefit from intra-session parallelism with real-time debate between agents.

**J1. Ensemble exploration via Agent Teams** (Medium)
Replace the current ensemble mechanism (N separate `claude -p` sessions + post-hoc synthesis agent) with a single Agent Team where teammates explore from different archetype lenses and debate in real-time. Requires J3 as prerequisite.

**J2. Collaborative decomposition** (Medium)
For `elmer implement`, spawn teammates to analyze different codebase aspects and debate step ordering before the lead produces the final plan. Requires J3 as prerequisite.

**J3. Headless Agent Teams feasibility** (Small — research)
The blocking question for J1 and J2: can `claude -p` (print mode) create and coordinate Agent Teams? Test whether team coordination works in headless mode.

**J4. Inter-exploration messaging** (Large)
Concurrent Elmer explorations on the same project could form an ad-hoc team, sharing findings via the mailbox system. Major architectural tension: Agent Teams are session-scoped, Elmer explorations are persistent. Depends on J3 feasibility results.

---

## Deferred / Uncertain

See Open Questions in CONTEXT.md. Features discussed but not committed are tracked there.

*Last updated: 2026-02-26, collapsed resolved directions to one-liners; 12 remaining future directions (B2, C4, D3, D5, E1, E2, G4, I2, J1–J4)*
