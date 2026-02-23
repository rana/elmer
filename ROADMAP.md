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

## Phase 2: Intelligence — COMPLETE

AI-driven topic generation, exploration chaining, and auto-approve. The system starts thinking about what to explore, not just executing what you tell it.

### Features

#### Topic Generation — COMPLETE
- [x] `elmer generate --count N` — AI reads project docs, proposes N research topics
- [x] `elmer generate --count N --follow-up ID` — AI generates follow-ups to a completed exploration
- [x] Topic generation uses a meta-prompt: "Given this project's state, what's worth exploring?"
- [x] Output: topics auto-spawned as separate explorations (or `--dry-run` to preview)
- [x] `generate-topics.md` archetype for meta-prompting

#### DAG Dependencies — COMPLETE
- [x] `--depends-on ID` — exploration only starts after dependency is approved/merged
- [x] Implicit chaining: follow-up explorations depend on their parent
- [x] `elmer tree` — visualize exploration DAG (text-based tree view)
- [x] Scheduler: on each `elmer status` or `approve`, start unblocked explorations
- [x] `dependencies` table in SQLite for many-to-many dependency tracking

#### Auto-Approve — COMPLETE
- [x] `--auto-approve` flag on explore and generate
- [x] AI review gate: spawn a second `claude -p` session to evaluate the proposal
- [x] Configurable criteria in `.elmer/config.toml`:
  ```toml
  [auto_approve]
  model = "sonnet"
  max_turns = 3
  criteria = "document-only proposals with no code changes"
  max_files_changed = 10
  require_proposal = true
  ```
- [x] Conservative default: reject when uncertain, queue for human review
- [x] `review-gate.md` archetype for review prompting

#### Two-Stage Prompt Generation — COMPLETE
- [x] Instead of static `$TOPIC` substitution, AI generates the optimal exploration prompt
- [x] Stage 1: `claude -p "Given this project and topic, generate the best exploration prompt"`
- [x] Stage 2: execute the generated prompt in the worktree
- [x] Archetype becomes a hint, not a rigid template — AI can combine or ignore archetypes
- [x] Fallback: `--no-generate` to use static templates (Phase 1 behavior)
- [x] `prompt-gen.md` archetype for meta-prompting

#### Cost Controls — COMPLETE
- [x] `--model haiku` for cheap broad exploration, `opus` for deep single-topic work
- [x] `--budget` on `elmer explore` — per-exploration cap via `claude --max-budget-usd`
- [x] `--budget` on `elmer generate` — total budget divided across spawned explorations
- [x] Token usage tracking in SQLite via `claude --output-format json`
- [x] Cost extraction from JSON log files on exploration completion
- [x] Meta-operation cost tracking (topic generation, auto-approve, prompt generation)
- [x] `elmer costs` — cost summary by exploration and meta-operation
- [x] Configurable cost rates in `[costs.rates]` config section

#### Archetype Evolution — COMPLETE
- [x] New archetypes: `adr-proposal.md`, `question-cluster.md`, `benchmark.md`, `dead-end-analysis.md`, `devil-advocate.md`
- [x] AI archetype selection: `--auto-archetype` flag, `select-archetype.md` meta-prompt, `archselect.py` module
- [x] User can still force archetype with `-a` (overrides `--auto-archetype`)
- [x] `[archetype_selection]` config section for model/max_turns defaults
- [x] Cost tracking for archetype selection as `archetype_select` meta-operation

### Phase Gate
AI-generated topics produce useful explorations. At least one auto-approved proposal is correct (no human would have rejected it). DAG chaining produces deeper research than independent explorations.

---

## Phase 3: Autonomy — COMPLETE

Continuous operation. Elmer runs as a daemon, generates its own research agenda, chains explorations, and grows a research tree autonomously.

### Features

#### Daemon — COMPLETE
- [x] `elmer daemon --interval 600` — continuous loop with configurable interval
- [x] Each cycle: harvest completed → gate (auto/human) → merge approved → start unblocked → generate new topics (if below threshold)
- [x] `elmer daemon --auto-approve --generate` — full autonomy mode
- [x] `elmer daemon --budget 5.00` — cost cap per cycle
- [x] Graceful shutdown (SIGINT/SIGTERM completes current cycle)
- [x] PID file at `.elmer/daemon.pid` for status checks
- [x] `elmer daemon status` / `elmer daemon stop`
- [x] `[daemon]` config section with all defaults
- [x] `daemon_log` table for cycle history tracking
- [x] `--max-concurrent` to limit parallel explorations
- [x] `--generate-threshold` / `--generate-count` for topic replenishment
- [x] Logging to `.elmer/logs/daemon.log`

#### Exploration Chains with Conditional Branching — COMPLETE
- [x] `--on-approve "elmer generate --follow-up $ID --count 3"` — trigger on approval
- [x] `--on-reject "elmer explore 'alternative to $TOPIC'"` — trigger on rejection
- [x] Research tree grows conditionally: approval spawns follow-ups, rejection redirects
- [x] `on_approve` / `on_reject` columns in explorations table
- [x] Shell commands with $ID and $TOPIC substitution, 5-minute timeout

#### Follow-Up Generation — COMPLETE
- [x] `elmer approve ID --auto-followup` — generates follow-up topics after merge
- [x] `--followup-count N` to control number of topics
- [x] `elmer approve --all --auto-followup` — follow-ups for all approved
- [x] `[followup]` config section (enabled, count, model, auto_approve)
- [x] Daemon integration: `--auto-followup` flag on daemon for continuous follow-ups
- [x] Follow-ups use `generate_topics(follow_up_id=...)` and inherit parent archetype/model

#### Cross-Project Insight Log — COMPLETE
- [x] `~/.elmer/insights.db` — shared SQLite database across projects
- [x] Post-approval insight extraction via `extract-insights.md` meta-prompt
- [x] Keyword-based relevance matching for cross-project injection into prompts
- [x] `[insights]` config section (enabled, model, max_turns, inject, inject_limit)
- [x] `elmer insights` — list all stored insights
- [x] Best-effort: extraction/injection failures never block exploration flow
- [x] Cost tracked as `extract_insights` meta-operation

#### Question Mining — COMPLETE
- [x] `elmer mine-questions` — extract open questions from project docs using AI
- [x] `mine-questions.md` meta-prompt reads project docs, outputs clustered questions
- [x] `--cluster` filter for targeting specific question themes
- [x] `--spawn` to convert questions to explorations and start them
- [x] `--max-per-cluster` to control topic explosion
- [x] `[questions]` config section (model, max_turns)
- [x] Cost tracked as `mine_questions` meta-operation

### Phase Gate
Daemon runs overnight on Mercury, produces 5+ proposals, at least 2 are worth merging. Research tree depth > 2 (follow-ups of follow-ups). Cross-project insight demonstrably improves exploration quality.

---

## Phase 4: Meta — COMPLETE

Elmer becomes a tool for managing how projects are researched, not just executing research. Template evolution, attention routing, project scaffolding.

### Features

#### Project Scaffolding — COMPLETE
- [x] `elmer init --docs` — scaffold the five-document pattern (CONTEXT.md, DESIGN.md, DECISIONS.md, ROADMAP.md, CLAUDE.md)
- [x] Templates for each document with project-agnostic structure using `{project_name}` substitution
- [x] Only creates files that don't already exist — safe to run repeatedly
- [x] Makes any project Elmer-ready and Claude Code-effective
- [x] Optional, not required — Elmer works without these documents

#### Template Evolution — COMPLETE
- [x] `elmer archetypes stats` — approval rate, average cost, and counts per archetype
- [x] `elmer archetypes list` — shows all available archetypes (local + bundled)
- [x] Stats computed from existing exploration data — no new tables needed
- [x] Highlights top-performing archetype when sufficient data exists

#### Attention Routing — COMPLETE
- [x] `elmer review --prioritize` — rank pending proposals by review priority
- [x] Heuristic scoring: dependents blocked (+30), staleness (+1/hr), small diff (+10), failed (+5)
- [x] Fast, free, transparent — no AI call, scores and reasons displayed
- [x] Helps manage review queue when daemon generates many proposals

#### Document Invariant Enforcement — COMPLETE
- [x] `elmer validate` — standalone document consistency check
- [x] `elmer approve ID --validate-invariants` — post-merge validation
- [x] AI checks and auto-fixes: ADR counts, phase status, feature claims
- [x] Default rules match CLAUDE.md "Document Invariants" section
- [x] Custom rules configurable in `[invariants] rules` in config.toml
- [x] `validate-invariants.md` meta-prompt archetype
- [x] Cost tracked as `validate_invariants` meta-operation

#### Multi-Project Dashboard — COMPLETE
- [x] `elmer status --all-projects` — overview across all registered projects
- [x] Global project registry at `~/.elmer/projects.json` (auto-updated on init/command use)
- [x] Aggregated status counts (running, done, pending, approved, rejected, failed) per project
- [x] Total cost per project and grand totals across projects
- [x] Stale registry entries auto-pruned on read

#### PR-Based Review — COMPLETE
- [x] `elmer pr ID` — push branch and create GitHub PR
- [x] PROPOSAL.md content becomes PR body
- [x] Uses `gh` CLI for GitHub integration (optional dependency)
- [x] PR title auto-generated from exploration topic
- [x] Works with explorations in done, failed, or running status

#### Claude Code Skill Scaffolding — COMPLETE
- [x] `elmer init --skills` — detect project characteristics and generate Claude Code skills
- [x] Signal detection from project docs (mission principles, i18n, personas, compliance)
- [x] Four skill templates: `mission-align`, `cultural-lens`, `persona-ux`, `compliance-check`
- [x] Only creates skills that don't already exist — safe to run repeatedly
- [x] Generates `.claude/skills/<name>/SKILL.md` with proper frontmatter and `$ARGUMENTS` substitution
- [x] Bridges Elmer's autonomous exploration with Claude Code's interactive analysis

### Phase Gate
`elmer init --docs` used to scaffold a new project. Template evolution demonstrably improves archetype quality over time. Attention routing helps a user managing 10+ pending proposals across 2+ projects.

---

## Deferred / Uncertain

Features discussed but not committed to a phase:

- **Shared template library** — single source for analysis methodology shared between Elmer archetypes and Claude Code skills. Deferred because drift between the two systems is tolerable and the indirection cost exceeds the sync benefit. Revisit if methodology divergence becomes painful.
- **Web UI for review** — local web server showing proposals with rich formatting. CLI review is sufficient for now.
- **Elmer-on-Elmer recursion** — Elmer running explorations on its own codebase. Philosophically interesting, practically requires CONTEXT.md.
- **Agent Teams integration** — within a single exploration, the Claude session could use Agent Teams for parallel sub-tasks. Emergent from claude's own capabilities, no Elmer changes needed.
- **MCP server** — expose Elmer state as an MCP tool for other AI systems to query.

*Last updated: coherence audit — Forge-on-Forge → Elmer-on-Elmer*
