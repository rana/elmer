# Elmer — Roadmap

All six phases complete. Git history has the full delivery record.

## Phase 1: Core Loop — COMPLETE

Manual explore → review → approve/decline. CLI primitives, git worktree isolation, SQLite state, three archetypes. Proved the loop is useful on a real project.

## Phase 2: Intelligence — COMPLETE

AI topic generation, DAG dependencies, auto-approve gate, two-stage prompt generation, cost controls, archetype evolution (8 exploration archetypes + AI selection).

## Phase 3: Autonomy — COMPLETE

Daemon loop, conditional chain actions, follow-up generation, cross-project insight log, question mining. Overnight autonomous operation with budget caps.

## Phase 4: Meta — COMPLETE

Project scaffolding, template evolution stats, attention routing, document invariant enforcement, multi-project dashboard, PR-based review, batch topic lists, skill scaffolding.

## Phase 5: Integration — COMPLETE

MCP server exposing full Elmer functionality as structured tools (ADR-024). 18 tools over stdio JSON-RPC: 6 read-only (status, review with prioritization, costs, tree, archetypes, insights) + 8 mutation (explore, approve with bulk/followup/invariants, amend, decline, cancel, retry, clean, pr) + 3 intelligence (generate, validate, mine-questions) + 1 batch. Custom subagent integration converting all archetypes and meta-operations to Claude Code subagents with tool restrictions and model selection (ADR-026). Proposal amendment workflow (`elmer amend`, ADR-028).

## Phase 6: Convergence — COMPLETE

Decline reasons (`elmer decline ID "reason"`), convergence digests (`elmer digest`), digest-aware topic generation, daemon synthesis step with threshold trigger (ADR-030). Closes the feedback loop: explorations accumulate understanding, not just output. 21 MCP tools (added `elmer_digest`, `elmer_config_get`, `elmer_recover_partial`; preview/dry-run modes on `elmer_clean`, `elmer_validate`, `elmer_amend`; progress indicators on `elmer_status`; stagger on `elmer_batch`; digest metadata on `elmer_generate`). Daemon loop gains a two-timescale architecture: fast loop (explore → approve) and slow loop (digest → generate → explore).

Ensemble exploration (ADR-031): `--replicas N` on `explore` and `batch` runs the same topic N times with independent sessions, then auto-synthesizes into a single consolidated proposal. Archetype rotation (`--archetypes`) and model rotation (`--models`) maximize variance. Approval/decline cascades: approving synthesis cleans up replicas, declining synthesis declines all. New `synthesize.py` module, `elmer-meta-synthesize` agent, daemon integration. Two-scale convergence: ensemble (intra-topic) and digest (inter-topic).

---

## Deferred / Uncertain

See Open Questions in CONTEXT.md. Features discussed but not committed are tracked there.

*Last updated: 2026-02-23, ADR-031 ensemble exploration and synthesis*
