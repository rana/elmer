# Elmer — Usage Guide

How to use Elmer effectively. README.md is the reference (what commands exist). This is the playbook (how to think about using them).

## The Core Loop

Everything in Elmer is built on one loop:

```
think of a question → explore it on a branch → review the proposal → merge or discard
```

```bash
elmer explore "should we use WebSockets or SSE for real-time updates"
# ... wait for Claude to finish ...
elmer status
elmer review should-we-use-websockets
elmer approve should-we-use-websockets   # or: elmer reject
```

That's it. Everything else is automation around this loop.

## Getting Started with a Project

### 1. Initialize

```bash
cd your-project
elmer init --docs
```

This creates `.elmer/` (config, archetypes, state) and scaffolds five project documents: CLAUDE.md, DESIGN.md, DECISIONS.md, ROADMAP.md, CONTEXT.md. These documents make Claude Code sessions more effective — they give Claude context about your project's architecture, decisions, and current state.

If you already have these documents, `--docs` won't overwrite them. If you don't want them, `elmer init` without `--docs` works fine — Elmer doesn't require them.

Optionally, scaffold Claude Code skills too:

```bash
elmer init --skills
```

This reads your project docs and generates `.claude/skills/` with project-specific analysis lenses (e.g., `/mission-align`, `/cultural-lens`). These complement Elmer's autonomous archetypes with interactive skills you can invoke in Claude Code sessions.

### 2. Edit .elmer/config.toml

The defaults work, but review them:

```toml
[defaults]
archetype = "explore-act"    # what style of exploration
model = "opus"               # which model (opus, sonnet, haiku)
max_turns = 50               # how long Claude works before stopping
```

**Model choice matters:**
- **opus** — deep, thorough analysis. Use for important questions. Costs more.
- **sonnet** — good balance. Use for most explorations.
- **haiku** — fast and cheap. Use for broad sweeps, quick questions, or when you want many explorations and will filter later.

### 3. Start exploring

Ask the first question that matters to your project right now:

```bash
elmer explore "what are the biggest architectural risks in this codebase"
```

## Choosing the Right Archetype

Archetypes shape *how* Claude explores. The topic is *what* to explore. Choosing the right archetype is the most impactful decision you make per exploration.

| When you want... | Use this archetype | Example |
|---|---|---|
| Analysis without code changes | `explore` | "What are the tradeoffs of our current caching strategy" |
| Analysis with concrete proposals | `explore-act` | "How should we handle authentication for the API" |
| Working code on the branch | `prototype` | "Build a CLI command for data export" |
| A formal architecture decision | `adr-proposal` | "Should we migrate from REST to GraphQL" |
| To stress-test a decision | `devil-advocate` | "Challenge our decision to use microservices" |
| To evaluate if something is worth doing | `dead-end-analysis` | "Is migrating to the new ORM worth the effort" |
| To measure something | `benchmark` | "Profile the search endpoint under load" |
| To explore a cluster of related questions | `question-cluster` | "Open questions about our deployment pipeline" |

**Default is `explore-act`** — analysis biased toward action. This is the right default for most work because it produces proposals you can act on, not just observations.

Use `--auto-archetype` to let AI pick:

```bash
elmer explore "topic" --auto-archetype
```

This costs a small meta-operation (sonnet, 3 turns) but often picks well, especially when the right archetype isn't obvious.

## Workflows

### Workflow 1: Single Focused Question

You have one question. You want a thorough answer.

```bash
elmer explore "should we switch from REST to GraphQL for the mobile API" -m opus
elmer status                          # check when done
elmer review should-we-switch         # read the proposal
elmer approve should-we-switch        # merge it
```

This is the simplest workflow. One exploration, one review, one decision.

### Workflow 2: Broad Survey

You want to understand a large space quickly. Generate many cheap explorations and filter.

```bash
elmer generate --count 10 -m haiku --dry-run   # preview AI-generated topics
elmer generate --count 10 -m haiku              # spawn them all
elmer status                                     # watch progress
elmer review --prioritize                        # review most impactful first
```

Or write your own topic list:

```bash
# Create .elmer/explore.md with your topics, then:
elmer batch .elmer/explore.md
```

Haiku is ideal here — fast, cheap, and the proposals tell you which topics deserve deeper investigation with opus.

### Workflow 3: Systematic Refactoring

You have a list of specific changes. They might touch overlapping files. You want them applied sequentially.

Create `.elmer/prototype.md`:

```markdown
# Refactoring plan

---

Extract validation logic from UserController into a UserValidator class.
Move all validation rules. Update the controller to delegate.

---

Extract validation logic from OrderController into an OrderValidator class.
Same pattern as UserValidator.

---

Create a shared ValidationResult type used by both validators.
Update both validators to return it.

---
```

Run with `--chain`:

```bash
elmer batch .elmer/prototype.md --chain
```

This creates a dependency chain: each exploration starts only after the previous one is approved and merged. No merge conflicts because each one works on the latest code.

As each completes:

```bash
elmer status              # see which is done
elmer review <id>         # check the work
elmer approve <id>        # merge — next one starts automatically
```

### Workflow 4: Research Tree

Start with one question, generate follow-ups, build a tree.

```bash
elmer explore "evaluate our error handling strategy" --auto-approve
# When done and auto-approved:
elmer approve evaluate-our-error --auto-followup --followup-count 3
```

This approves the exploration, then AI generates 3 follow-up topics and spawns them. Each follow-up might generate its own follow-ups. The tree grows.

Use `elmer tree` to visualize:

```
* evaluate-our-error [approved]
    ├── * error-handling-in-api-layer [done]
    ├── ~ error-recovery-patterns [running]
    └── . retry-strategy-for-external [pending]
```

### Workflow 5: Overnight Daemon

Let Elmer run continuously. It generates topics, spawns explorations, auto-reviews, and queues results for you.

```bash
elmer daemon --auto-approve --generate --budget 5.00
```

Come back in the morning:

```bash
elmer status                 # see what happened
elmer review --prioritize    # review the queue
elmer costs                  # check spending
```

Conservative start: set a budget, use `--max-concurrent 2` to limit parallelism, and review everything manually the first few times before enabling `--auto-approve`.

### Workflow 6: Autonomous Pipeline

Combine batch with auto-approve for fully hands-off sequential work:

```bash
elmer batch .elmer/prototype.md --chain --auto-approve
```

Each topic is explored, AI-reviewed, and if approved, merged — then the next topic starts on the updated code. You review the results after the entire pipeline completes.

Use this when you trust the archetype and the topics are well-defined (e.g., mechanical refactoring, documentation updates, test additions).

## Writing Good Topics

A topic is the question or task you give to Claude. It's the `$TOPIC` in the archetype template. Good topics produce good proposals.

**Be specific about what you want to know or do:**

| Vague (produces vague proposals) | Specific (produces actionable proposals) |
|---|---|
| "improve performance" | "profile the /search endpoint and identify the top 3 bottlenecks" |
| "fix the tests" | "investigate why test_order_processing is flaky under concurrent access" |
| "add caching" | "evaluate Redis vs in-memory caching for the product catalog, considering our 99th percentile latency target of 50ms" |
| "refactor auth" | "extract the JWT validation logic from middleware.py into a dedicated auth module that can be unit tested independently" |

**Include context and constraints when relevant:**

```
Evaluate whether we should replace our hand-rolled form validation with Zod.
Consider: we have 47 forms, 12 shared validation rules, and 3 developers.
The current system works but is hard to test and has no TypeScript integration.
```

**For prototype archetypes, be explicit about what "done" looks like:**

```
Build a CLI command `export-data` that:
- Accepts --format (csv, json, parquet)
- Reads from the analytics database
- Supports date range filtering with --from and --to
- Writes to stdout by default, --output for file
```

## Writing Topic List Files

Topic list files live in `.elmer/` and are named after their archetype. Format:

```markdown
# Optional header — ignored by parser

---

First topic goes here. Can be multi-line.
Include as much context as needed.

---

Second topic.

---

Third topic.

---
```

**Tips:**

- The `#` header is a good place for notes about why these topics exist and when to re-run them.
- Multi-line topics work well for `prototype` (detailed specs) and `explore-act` (questions with constraints).
- Keep `explore` topics to 1-2 sentences — more context comes from the project docs Claude reads.
- The file is committed to git — it's project knowledge. Update it as priorities change.
- Use `--dry-run` to verify parsing before spawning.

**When to use `--chain` vs. parallel:**

- **Chain** when topics modify overlapping files (refactoring, migrations, sequential upgrades).
- **Parallel** (default) when topics are independent (research questions, analysis, audits of different subsystems).

## Cost Management

Elmer spawns `claude -p` sessions. Each session costs money. Here's how to control it.

**Per-exploration budget:**

```bash
elmer explore "topic" --budget 2.00              # cap at $2
elmer batch .elmer/explore-act.md --budget 10    # $10 total, divided across topics
```

**Model selection is the biggest cost lever:**

| Model | Relative cost | Good for |
|---|---|---|
| haiku | 1x | Quick surveys, broad generation, simple questions |
| sonnet | ~10x | Most explorations, meta-operations, reviews |
| opus | ~50x | Deep analysis, complex prototyping, critical decisions |

**Track costs:**

```bash
elmer costs                        # summary of all spending
elmer costs --exploration my-topic # detail for one exploration
```

**Cost-conscious workflow:**

1. Generate topics with haiku (`elmer generate -m haiku --count 10`)
2. Review the list, pick the 3 best
3. Run those 3 with sonnet or opus
4. Use auto-approve with sonnet for the review gate (cheaper than opus)

## Understanding Exploration States

```
pending → running → done → approved
                         → rejected
                  → failed → rejected
```

- **pending**: Waiting for a dependency to be approved. No worktree yet. Will start automatically when unblocked.
- **running**: Claude session active. Check `.elmer/logs/<id>.log` for progress.
- **done**: Session finished. PROPOSAL.md exists on the branch. Ready for review.
- **failed**: Session finished but no PROPOSAL.md. Check the log. You can still approve (to merge any other changes) or reject.
- **approved**: Branch merged. Worktree cleaned up.
- **rejected**: Branch deleted. Worktree cleaned up. Log preserved.

## Patterns That Work Well

**Start narrow, go broad.** One manual exploration on a specific question. If the answer opens more questions, use `--auto-followup` or `elmer generate --follow-up ID`.

**Cheap filter, expensive deep-dive.** Use haiku to survey 10 topics. Read the proposals. Re-explore the 2 most promising with opus.

**Prototype on a branch, review the diff.** The `prototype` archetype writes code on the branch. Use `elmer review ID` to see PROPOSAL.md, then look at the actual git diff with `git diff main...elmer/<id>`.

**Audit rotation.** Configure daemon with audit archetypes that rotate through subsystems:

```toml
[audit]
enabled = true
schedule = [
  "consistency-audit:data model",
  "architecture-audit:API layer",
  "documentation-audit:",
  "opportunity-scan:",
]
```

Each daemon cycle runs one audit. Over a week, every subsystem gets checked.

**Question mining as a starting point.** When you don't know what to explore:

```bash
elmer mine-questions                   # see what's open
elmer mine-questions --spawn           # explore everything
elmer mine-questions --cluster "API"   # just one area
```

## When to Use Elmer vs Claude Code Skills

Elmer and Claude Code skills overlap in analysis methodology but serve different moments. Use both.

| Situation | Use | Why |
|-----------|-----|-----|
| Deep overnight research | `elmer explore` or `elmer daemon` | Background execution, persistent state, branch isolation |
| Quick interactive audit | `/coherence` or `/gaps` | In-session, conversational, iterate with follow-ups |
| Batch refactoring | `elmer batch .elmer/prototype.md --chain` | Worktree isolation, sequential merging, no conflicts |
| Design review with feedback loop | `/mission-align` or `/deep-review` | Interactive, you steer the analysis in real-time |
| Don't know what to explore | `elmer mine-questions` or `elmer generate` | AI generates topics autonomously |
| Check a specific concern | `/cultural-lens "rural India"` | Focused, immediate, argumentized |

**The general rule:** If you need persistence, parallelism, or autonomy — use Elmer. If you need interactivity, iteration, or immediacy — use a skill. If you're setting up a project, use both: `elmer init --docs --skills`.

## Common Mistakes

**Too many concurrent explorations.** Each one is a `claude -p` process. Start with 2-3. Scale up once you're comfortable reviewing the output.

**Auto-approve too early.** Review proposals manually until you understand what quality looks like for your project. Then enable auto-approve for specific archetypes (like audits and documentation) where false positives are low-risk.

**Vague topics with prototype archetype.** If you tell Claude to "improve the code" with the prototype archetype, it will change code. Be specific about what should change and what should not.

**Ignoring costs.** Run `elmer costs` regularly. Set `--budget` on daemon runs. Opus is powerful but expensive — don't run it on 10 topics unless you mean to.

**Not using --chain for related changes.** If topics A, B, and C all modify `config.py`, run them with `--chain`. Otherwise you'll get merge conflicts on approve.

## Quick Reference

```bash
# "I have one question"
elmer explore "my question"

# "I have a list of things to investigate"
elmer batch .elmer/explore-act.md

# "I have a list of code changes"
elmer batch .elmer/prototype.md --chain

# "I don't know what to explore"
elmer mine-questions --spawn

# "Let AI figure out what to explore"
elmer generate

# "What's the status"
elmer status

# "What should I review first"
elmer review --prioritize

# "Approve everything"
elmer approve --all

# "How much did this cost"
elmer costs

# "Run it overnight"
elmer daemon --auto-approve --generate --budget 5.00
```
