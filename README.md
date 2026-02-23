# Elmer

Autonomous research with branching.

*"Be vewy vewy quiet, I'm hunting insights."*

Elmer creates git branches, spawns Claude Code sessions to explore topics autonomously, and queues proposals for your review. Approve to merge. Reject to discard. Let it run overnight.

## How It Works

```
topic → git worktree → claude -p → PROPOSAL.md → human review → merge or discard
```

Each exploration gets its own git branch and worktree. A background Claude Code session runs against the worktree, reads the project's documentation, investigates the topic, and writes a PROPOSAL.md. You review proposals and approve or reject them.

## Install

```bash
uv tool install /path/to/elmer
# or
pip install /path/to/elmer
```

## Quick Start

```bash
# In any git repo:
elmer init
elmer init --docs                     # Also scaffold project documentation

# Start explorations
elmer explore "evaluate COT positioning as 6th data axis"
elmer explore "prototype hybrid search API" -a prototype -m opus

# Check progress
elmer status

# Review proposals
elmer review                          # list pending
elmer review --prioritize             # rank by review priority
elmer review evaluate-cot-positioning # read full proposal

# Approve or reject
elmer approve evaluate-cot-positioning
elmer reject prototype-hybrid-search

# Clean up
elmer clean
```

## Commands

| Command | Description |
|---------|-------------|
| `elmer init` | Initialize `.elmer/` in the current project |
| `elmer init --docs` | Also scaffold CLAUDE.md, DESIGN.md, DECISIONS.md, ROADMAP.md, CONTEXT.md |
| `elmer explore "topic"` | Start an exploration on a new branch |
| `elmer explore -f topics.txt` | Batch explore from a file (one topic per line) |
| `elmer batch .elmer/explore-act.md` | Run explorations from a topic list file |
| `elmer batch FILE --chain` | Run topics sequentially (each depends on previous) |
| `elmer batch FILE --dry-run` | Preview parsed topics without spawning |
| `elmer generate` | AI-generate research topics and spawn explorations |
| `elmer status` | Show all explorations and their states |
| `elmer tree` | Show exploration dependency tree |
| `elmer review` | List proposals pending review |
| `elmer review --prioritize` | Rank proposals by review priority |
| `elmer review ID` | Show a full proposal |
| `elmer approve ID` | Merge exploration branch and clean up |
| `elmer approve --all` | Approve all pending proposals |
| `elmer approve ID --auto-followup` | Approve and generate follow-up topics |
| `elmer approve ID --validate-invariants` | Check doc consistency after merge |
| `elmer reject ID` | Discard branch and clean up |
| `elmer costs` | Show cost summary for all explorations |
| `elmer validate` | Check document invariants |
| `elmer archetypes list` | List available archetypes |
| `elmer archetypes stats` | Show archetype effectiveness statistics |
| `elmer mine-questions` | Extract open questions from project docs |
| `elmer mine-questions --spawn` | Mine questions and explore them |
| `elmer insights` | List cross-project insights |
| `elmer daemon` | Start the daemon for continuous operation |
| `elmer daemon status` | Check if the daemon is running |
| `elmer daemon stop` | Gracefully stop the daemon |
| `elmer status --all-projects` | Show status across all registered projects |
| `elmer pr ID` | Push branch and create GitHub PR |
| `elmer clean` | Remove finished worktrees and state entries |

## Options

```bash
# Explore options
elmer explore "topic" -a prototype     # Use prototype archetype (default: explore-act)
elmer explore "topic" -m sonnet        # Use sonnet model (default: opus)
elmer explore "topic" --max-turns 100  # Increase turn limit (default: 50)
elmer explore "topic" --auto-archetype # AI picks the best archetype for the topic
elmer explore "topic" --auto-approve   # AI reviews proposal when done
elmer explore "topic" --generate-prompt # AI generates the exploration prompt
elmer explore "topic" --budget 2.00    # Cap cost at $2
elmer explore "topic" --on-approve "elmer generate --follow-up \$ID"  # Chain on approval
elmer explore "topic" --on-reject "elmer explore 'alternative to \$TOPIC'"  # Chain on rejection

# Review options
elmer review --prioritize              # Rank by blockers, staleness, diff size
elmer approve ID --validate-invariants # Check doc consistency after merge

# Archetype analysis
elmer archetypes list                  # Show all archetypes
elmer archetypes stats                 # Approval rates and metrics per archetype

# Question mining
elmer mine-questions                    # Show question clusters
elmer mine-questions --cluster "API"    # Filter to a cluster
elmer mine-questions --spawn            # Explore all mined questions
elmer mine-questions --spawn --cluster "Design"  # Explore one cluster

# Batch topic lists
elmer batch .elmer/explore-act.md              # Spawn all topics with explore-act
elmer batch .elmer/prototype.md --chain        # Sequential — no merge conflicts
elmer batch .elmer/explore-act.md --item 3     # Run only item 3
elmer batch .elmer/explore-act.md --budget 10  # $10 divided across topics
elmer batch .elmer/explore-act.md --auto-approve --chain  # Fully autonomous pipeline

# Multi-project
elmer status --all-projects            # Aggregated status across all projects

# Pull requests (requires gh CLI)
elmer pr my-exploration                # Push branch and create GitHub PR

# Daemon options
elmer daemon --interval 300            # 5-minute cycle interval
elmer daemon --auto-approve --generate # Full autonomy mode
elmer daemon --budget 5.00             # Cost cap per cycle
elmer daemon --max-concurrent 3        # Limit parallel explorations
elmer daemon --auto-followup           # Generate follow-ups after approvals
```

## Archetypes

Archetypes are prompt templates that shape how Claude explores a topic.

| Archetype | Purpose |
|-----------|---------|
| `explore` | Read-only analysis — think deeply, no action bias |
| `explore-act` | Analysis biased toward concrete action proposals |
| `prototype` | Write working code on the branch |
| `adr-proposal` | Propose architecture decisions with alternatives |
| `question-cluster` | Explore clusters of related open questions |
| `benchmark` | Measure, evaluate, and recommend improvements |
| `dead-end-analysis` | Analyze whether a direction is worth pursuing |
| `devil-advocate` | Challenge assumptions and decisions |

Use `--auto-archetype` to let AI pick the best archetype for each topic. Use `-a` to force a specific one.

Archetypes live in `.elmer/archetypes/`. Add your own by creating a markdown file with `$TOPIC` as the placeholder. Use `elmer archetypes stats` to see which perform best.

## Topic List Files

Create a markdown file in `.elmer/` named after the archetype you want to use. Separate topics with `---`:

```markdown
# Refactoring priorities

---

Extract the validation logic from the controller into a dedicated validator module

---

Consolidate the three notification services into a unified notification gateway

---

Replace the hand-rolled SQL query builder with parameterized queries throughout

---
```

Save as `.elmer/prototype.md` and run:

```bash
elmer batch .elmer/prototype.md --chain    # sequential — each builds on previous merge
elmer batch .elmer/prototype.md --dry-run  # preview topics first
```

The archetype is inferred from the filename (`prototype.md` → `prototype` archetype). Use `-a` to override. Topics can be multi-line. The first section is ignored if it starts with `#` (use it for comments). Use `--chain` when topics might touch overlapping files — each exploration starts after the previous is approved and merged.

## Configuration

`.elmer/config.toml`:

```toml
[defaults]
archetype = "explore-act"
model = "opus"
max_turns = 50

[insights]
enabled = false          # Extract insights after approval
inject = true            # Inject cross-project insights into prompts

[invariants]
model = "sonnet"
max_turns = 5
# rules = ["ADR count in CLAUDE.md matches DECISIONS.md entries"]
```

## Prerequisites

- Git repository
- [Claude Code](https://claude.ai/claude-code) CLI (`claude` in PATH)
- Project should have appropriate tool permissions configured in `.claude/settings.json`
- [GitHub CLI](https://cli.github.com/) (`gh`) — optional, required for `elmer pr`

## Project Structure

When you run `elmer init`, it creates:

```
.elmer/
├── config.toml        # Configuration (committed)
├── archetypes/        # Prompt templates (committed)
│   ├── explore.md
│   ├── explore-act.md
│   └── prototype.md
├── explore-act.md     # Topic list file (optional, committed)
├── worktrees/         # Git worktrees (gitignored)
├── logs/              # Claude session logs (gitignored)
└── state.db           # SQLite state (gitignored)
```

With `--docs`, also creates in the project root:

```
CLAUDE.md              # Claude Code instructions
DESIGN.md              # Architecture and design
DECISIONS.md           # Architecture decision records
ROADMAP.md             # Phased development plan
CONTEXT.md             # Project context for AI assistants
```

## How Explorations Work

1. `elmer explore "topic"` creates a git worktree on branch `elmer/<slug>`
2. Loads the archetype template, substitutes `$TOPIC`
3. Spawns `claude -p "<prompt>"` in the worktree directory (background)
4. Claude reads project docs, investigates the topic, writes `PROPOSAL.md`
5. `elmer status` detects when the session finishes
6. `elmer review <id>` shows the proposal
7. `elmer approve <id>` merges the branch; `elmer reject <id>` discards it

## Using Elmer from Claude Code

Elmer is a CLI tool. The simplest way to use it from within a Claude Code session is to call it via the terminal:

```bash
elmer explore "evaluate caching strategies"
elmer status
elmer review evaluate-caching-strategies
elmer approve evaluate-caching-strategies
```

Claude Code learns the commands from the project's `CLAUDE.md`, which documents the full interface. No MCP server or special integration is needed — Elmer is designed to be called as a regular CLI tool.

Note that `elmer explore` spawns a background `claude -p` process, so running it from within Claude Code means nested Claude Code invocations. This works fine (they are separate processes) but be aware of the cost and concurrency implications.

## Name

Elmer Fudd. Persistent hunter. Homage to the [Ralph Wiggum](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) naming tradition for autonomous Claude Code tools.
