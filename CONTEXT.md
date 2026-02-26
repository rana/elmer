# Elmer — Context

## What Elmer Is

Elmer is an autonomous research tool for AI-assisted software development. It uses git branches as isolation boundaries and Claude Code sessions (`claude -p`) as workers. You ask a question or describe a task, Elmer explores it on a branch, and you review the result — approve to merge, decline to discard.

Elmer changes what a "session" means. Claude Code is the interactive layer for steering and review. Elmer is the autonomous layer that runs between sessions — start explorations, close your terminal, review tomorrow.

## Who It's For

Developers using Claude Code who want autonomous research, exploration, and prototyping that persists beyond a single session. Elmer is most useful when you have multiple questions to investigate, overlapping concerns to explore in parallel, or refactoring work that benefits from branch isolation and sequential merging.

## Project Methodology

This project is designed and maintained through AI-human collaboration. The human principal directs strategy, makes design decisions, and provides editorial judgment. The AI (Claude) serves as architect, implementer, and maintainer across sessions.

The documentation volume — CLAUDE.md, CONTEXT.md, DESIGN.md, DECISIONS.md, ROADMAP.md, GUIDE.md — is intentional: it is the project's institutional memory, enabling continuity across AI context windows where no persistent memory exists. Each document has a distinct role (see Canonical Homes in CLAUDE.md). Together, they allow any new session — human or AI — to understand the full state of the project without archeological effort.

This is the same pattern Elmer scaffolds for other projects via `elmer init --docs`. Elmer practices what it prescribes.

### AI-Human Collaboration Model

Elmer embodies a clear division of responsibility:

**Human decides:**
- What questions to explore (topics)
- How to explore them (archetype selection, model choice, budget)
- Whether to accept the result (approve/decline)
- When to grant autonomy (opt-in `--auto-approve`, `--auto-followup`, daemon mode)

**AI executes:**
- Autonomous exploration on isolated branches
- Topic generation from project context
- Proposal review (auto-approve gate)
- Insight extraction from approved work
- Question mining from documentation gaps

**The boundary:** AI proposes, human disposes. Every autonomy feature is opt-in. `--auto-approve` is conservative by default — it rejects when uncertain. The daemon respects budget caps. Chain actions are user-specified, never AI-generated. This is deliberate: the tool should extend human judgment, not replace it.

### Why Five Documents (Not One)

A single monolithic document fails at scale — it becomes too long to read, too broad to update surgically, and too tangled to maintain. The five-document pattern separates concerns:

| Document | Concern | Audience |
|----------|---------|----------|
| **CLAUDE.md** | Instructions — rules, constraints, conventions | AI (Claude Code) |
| **CONTEXT.md** | Background — methodology, purpose, current state | AI and human newcomers |
| **DESIGN.md** | Architecture — modules, data flow, schemas | Developers |
| **DECISIONS.md** | Rationale — why, not just what | Future decision-makers |
| **ROADMAP.md** | Timeline — what's done, what's next, what's deferred | Project managers |

GUIDE.md and README.md add user-facing documentation (playbook and reference, respectively). The separation means updating a design decision doesn't require re-reading installation instructions, and changing a CLI flag doesn't touch the architecture.

## Current State

All seven development phases complete:

1. **Phase 1 (Core Loop):** Manual explore/review/approve cycle. Proved the loop is useful.
2. **Phase 2 (Intelligence):** AI topic generation, DAG dependencies, auto-approve, cost controls.
3. **Phase 3 (Autonomy):** Daemon, chain actions, cross-project insights, question mining.
4. **Phase 4 (Meta):** Scaffolding, archetype stats, attention routing, invariant enforcement, multi-project dashboard, PR creation, batch topics, skill scaffolding.
5. **Phase 5 (Integration):** MCP server — structured Claude Code access, custom subagent integration, proposal amendment.
6. **Phase 6 (Convergence):** Decline reasons, convergence digests, digest-aware generation, daemon synthesis step. Closes the feedback loop.
7. **Phase 7 (Implementation Engine):** Milestone decomposition (`elmer implement`) — AI decomposes milestones into ordered plan steps with dependencies, then executes each as a separate exploration with cross-step context, verification hooks, auto-amend, and cascade failure handling. 11 ADRs (ADR-038 through ADR-048).

The tool is functional and in active use on multiple projects. 32 ADRs recorded.

## What's Working

- Core exploration loop is reliable — worktree isolation, background workers, state tracking
- Daemon mode runs overnight with budget caps
- Cross-project insights accumulate across approved explorations
- MCP server provides structured access for Claude Code integration (21 tools)
- Batch topics with `--chain` handle sequential refactoring without merge conflicts
- Five-document scaffolding (`elmer init --docs`) bootstraps effective AI-assisted projects
- Convergence digests synthesize understanding across approved/declined work
- Decline reasons create learning signals that steer future topic generation
- Ensemble exploration runs same topic N times with synthesis for high-confidence decisions
- Implementation engine decomposes milestones into executable plan steps with dependency tracking
- Plan steps carry cross-step context, verification hooks, and auto-amend retry on failure
- Daemon auto-retries failed plan steps with failure-aware context injection
- Parallel conflict detection warns about key_files overlap before execution

## Open Questions

- **Shared template library** between Elmer archetypes and Claude Code skills — deferred because drift is tolerable and the indirection cost exceeds the sync benefit
- **Web UI for review** — CLI review works but rich formatting would help for large proposals
- **Elmer-on-Elmer recursion** — running explorations on Elmer's own codebase (meta-tool use)
- **Scaffolding template quality** — generated CONTEXT.md is structural but not philosophical; could better teach the institutional memory pattern
- **Agent Teams integration** — within a single exploration, the Claude session could use Agent Teams for parallel sub-tasks. Partially addressed by ADR-026 (custom subagents). Agent Teams remain session-scoped and don't persist.
- **Sibling-aware exploration prompts** — explorations have no knowledge of other in-flight or completed explorations. Partially addressed by convergence digests (ADR-030): the digest synthesizes cross-exploration understanding, which feeds into topic generation. Individual explorations remain independent by design. The remaining question is whether to inject digest context into exploration prompts (not just generation prompts).
- **Cross-project MCP** — every MCP tool infers project from `cwd`. No way to address multiple projects in a single Claude Code session. Adding a `project_path` parameter to tools that need it is the likely path, with `None` defaulting to cwd. Deferred because most usage is single-project.
- **Composable status queries** — MCP status/review tools return full result sets; filtering happens client-side, wasting tokens. A `filter` parameter on `elmer_status` (e.g., `status=done AND archetype=prototype`) would collapse multi-call workflows. Deferred because current usage is manageable.
- **Document-heavy pre-code projects** — srf-yogananda-teachings (13 docs, 124 ADRs, 1.5 MB architecture, zero code) exposed that `elmer implement` assumes verification commands exist. Projects in design phase need document-coherence verification, not build/test. See Future Directions D1–D5 in ROADMAP.md.
- ~~**Retry dependency management**~~ — resolved in ADR-049. `_rebuild_plan_dependencies()` reconstructs the dependency graph from plan JSON after retries.
- ~~**Plan completion check ordering**~~ — resolved in ADR-049. Daemon runs pre-approval completion check in worktree before approving the last plan step.

*Last updated: 2026-02-25, A1+A2 resolved (ADR-049)*
