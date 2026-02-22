# Elmer — Roadmap

## Phase 1: Core Loop — COMPLETE

Manual explore → review → approve/reject. Proves the primitive is useful.

### Deliverables
- [x] `elmer init` — scaffold `.elmer/` in any git project
- [x] `elmer explore "topic"` — create worktree, spawn `claude -p`, track state
- [x] `elmer explore -f topics.txt` — batch exploration from file
- [x] `elmer status` — show all explorations with state transitions
- [x] `elmer review [ID]` — list pending or show full proposal
- [x] `elmer approve ID` / `elmer approve --all` — merge and cleanup
- [x] `elmer reject ID` — discard and cleanup
- [x] `elmer clean` — remove finished worktrees and state
- [x] Three archetypes: explore, explore-act, prototype
- [x] SQLite state tracking with PID-based completion detection
- [x] Git worktree isolation per exploration
- [x] End-to-end test: Mercury exploration produced substantive PROPOSAL.md (haiku, ~2 min)

### Phase Gate
Manual loop used on a real project, proposals reviewed, at least one approved or rejected. **PASSED.**

---

## Phase 2: Intelligence

AI-driven topic generation, exploration chaining, and auto-approve. The system starts thinking about what to explore, not just executing what you tell it.

### Features

#### Topic Generation
- `elmer generate --count N` — AI reads project docs, proposes N research topics
- `elmer generate --count N --follow-up ID` — AI generates follow-ups to a completed exploration
- Topic generation uses a meta-prompt: "Given this project's state, what's worth exploring?"
- Output: topics added to queue, each spawned as separate exploration

#### DAG Dependencies
- `--depends-on ID` — exploration only starts after dependency is approved/merged
- Implicit chaining: follow-up explorations depend on their parent
- `elmer tree` — visualize exploration DAG (text-based tree view)
- Scheduler: on each `elmer status` or daemon cycle, start unblocked explorations

#### Auto-Approve
- `--auto-approve` flag on explore or daemon
- AI review gate: spawn a second `claude -p` session to evaluate the proposal
- Configurable criteria in `.elmer/config.toml`:
  ```toml
  [auto_approve]
  enabled = false
  criteria = "document-only proposals, no code changes"
  max_files_changed = 5
  require_proposal = true
  ```
- Conservative default: reject when uncertain, queue for human review

#### Two-Stage Prompt Generation
- Instead of static `$TOPIC` substitution, AI generates the optimal exploration prompt
- Stage 1: `claude -p "Given this project and topic, generate the best exploration prompt"`
- Stage 2: execute the generated prompt in the worktree
- Archetype becomes a hint, not a rigid template — AI can combine or ignore archetypes
- Fallback: `--no-generate` to use static templates (Phase 1 behavior)

#### Cost Controls
- `--model haiku` for cheap broad exploration, `opus` for deep single-topic work
- `--budget 5.00` — cap total cost per daemon cycle
- Token usage tracking in SQLite (from claude output if available)
- `elmer costs` — cost summary by exploration, model, project

#### Archetype Evolution
- New archetypes: `adr-proposal.md`, `question-cluster.md`, `benchmark.md`, `dead-end-analysis.md`, `devil-advocate.md`
- AI archetype selection: given a topic, pick the best archetype from available set
- User can still force archetype with `-a`

### Phase Gate
AI-generated topics produce useful explorations. At least one auto-approved proposal is correct (no human would have rejected it). DAG chaining produces deeper research than independent explorations.

---

## Phase 3: Autonomy

Continuous operation. Elmer runs as a daemon, generates its own research agenda, chains explorations, and grows a research tree autonomously.

### Features

#### Daemon
- `elmer daemon --interval 10m` — continuous loop
- Each cycle: check completed → gate (auto/human) → merge approved → start unblocked → generate new topics (if below threshold)
- `elmer daemon --auto-approve --generate` — full autonomy mode
- `elmer daemon --budget 5.00` — cost cap per cycle
- Graceful shutdown (SIGINT/SIGTERM completes current cycle)
- PID file at `.elmer/daemon.pid` for status checks
- `elmer daemon status` / `elmer daemon stop`

#### Exploration Chains with Conditional Branching
- `--on-approve "elmer generate --follow-up $ID --count 3"` — trigger on approval
- `--on-reject "elmer explore 'alternative to $TOPIC'"` — trigger on rejection
- Research tree grows conditionally: approval spawns follow-ups, rejection redirects
- Tree visualization: `elmer tree` shows full exploration history with outcomes

#### Cross-Project Insight Log
- `~/.elmer/insights.db` — shared across projects
- When an exploration produces a generalizable insight, store it
- Future explorations get relevant cross-project insights injected into context
- Example: Mercury's "confirmation beats generation" finding → injected into SRF exploration prompts where relevant

#### Follow-Up Generation
- After merge, AI reads the merged proposal and project's updated state
- Generates follow-up topics based on what the proposal opened up
- Follow-ups automatically depend on the parent exploration
- Self-directing research tree: seed one topic, wake up to a tree of proposals

#### Question Mining
- `elmer mine-questions --project /path/to/project` — extract open questions from project docs
- Parses CONTEXT.md, DESIGN.md, ROADMAP.md for explicit questions and implicit gaps
- Clusters questions by theme
- `elmer generate --from-questions --cluster accessibility` — explore a question cluster

### Phase Gate
Daemon runs overnight on Mercury, produces 5+ proposals, at least 2 are worth merging. Research tree depth > 2 (follow-ups of follow-ups). Cross-project insight demonstrably improves exploration quality.

---

## Phase 4: Meta

Elmer becomes a tool for managing how projects are researched, not just executing research. Template evolution, attention routing, project scaffolding.

### Features

#### Project Scaffolding
- `elmer init --docs` — scaffold the five-document pattern (CONTEXT.md, DESIGN.md, DECISIONS.md, ROADMAP.md, CLAUDE.md)
- Templates for each document with project-agnostic structure
- Makes any project Elmer-ready and Claude Code-effective
- Optional, not required — Elmer works without these documents

#### Template Evolution
- Track which archetype/prompt combinations produce the best proposals
- "Best" measured by: approval rate, proposal length, follow-up generation, human feedback
- Extract successful generated prompts as new archetypes
- `elmer archetypes stats` — which archetypes produce the most approvals

#### Attention Routing
- `elmer review --prioritize` — rank pending proposals by expected value
- Ranking factors: estimated impact (AI assesses), chain dependencies (blockers rank higher), project priority (configurable), staleness (older first)
- With many explorations across projects, human attention is the bottleneck — routing helps

#### Document Invariant Enforcement
- Post-merge validation pass for projects with document invariants
- Example: Mercury requires decision counts to match across CLAUDE.md, CONTEXT.md, DECISIONS.md
- `elmer approve ID --validate-invariants` spawns a short `claude -p` session after merge to check and fix
- Project-specific invariant rules in `.elmer/config.toml`

#### Multi-Project Dashboard
- `elmer status --all-projects` — overview across all projects
- `elmer daemon` can manage multiple projects (configurable in `~/.elmer/config.toml`)
- Per-project config: templates, auto-approve criteria, budget, generation frequency

#### PR-Based Review
- `elmer explore "topic" --pr` — push branch, create GitHub PR
- Proposal becomes PR description
- Review via GitHub UI (comments, approval, merge)
- Integrates with existing code review workflows

### Phase Gate
`elmer init --docs` used to scaffold a new project. Template evolution demonstrably improves archetype quality over time. Attention routing helps a user managing 10+ pending proposals across 2+ projects.

---

## Deferred / Uncertain

Features discussed but not committed to a phase:

- **Claude Code plugin wrapper** — thin plugin providing `/elmer:status`, `/elmer:explore` from within sessions. Low priority since `elmer` CLI works from any terminal.
- **Web UI for review** — local web server showing proposals with rich formatting. CLI review is sufficient for now.
- **Forge-on-Forge recursion** — Elmer running explorations on its own codebase. Philosophically interesting, practically requires CONTEXT.md.
- **Agent Teams integration** — within a single exploration, the Claude session could use Agent Teams for parallel sub-tasks. Emergent from claude's own capabilities, no Elmer changes needed.
- **MCP server** — expose Elmer state as an MCP tool for other AI systems to query.

*Last updated: Phase 1 complete*
