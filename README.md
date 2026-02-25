# Elmer

Autonomous research with branching.

*"Be vewy vewy quiet, I'm hunting insights."*

Elmer creates git branches, spawns Claude Code sessions to explore topics autonomously, and queues proposals for your review. Approve to merge. Decline to discard. Let it run overnight.

## How It Works

```
topic → git worktree → claude -p → PROPOSAL.md → human review → merge or discard
```

Each exploration gets its own git branch and worktree. A background Claude Code session runs against the worktree, reads the project's documentation, investigates the topic, and writes a PROPOSAL.md. You review proposals and approve or decline them.

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
elmer init --skills                   # Also scaffold Claude Code skills
elmer init --agents                   # Scaffold subagent definitions for customization

# Start explorations
elmer explore "evaluate COT positioning as 6th data axis"
elmer explore "prototype hybrid search API" -a prototype -m opus

# Check progress
elmer status

# Review proposals
elmer review                          # list pending
elmer review --prioritize             # rank by review priority
elmer review evaluate-cot-positioning # read full proposal

# Approve or decline
elmer approve evaluate-cot-positioning
elmer decline prototype-hybrid-search

# Clean up
elmer clean
```

## Commands

| Command | Description |
|---------|-------------|
| `elmer init` | Initialize `.elmer/` in the current project |
| `elmer init --docs` | Also scaffold CLAUDE.md, DESIGN.md, DECISIONS.md, ROADMAP.md, CONTEXT.md |
| `elmer init --skills` | Scaffold Claude Code skills from project docs |
| `elmer init --agents` | Scaffold Claude Code subagent definitions to `.claude/agents/` |
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
| `elmer amend ID "feedback"` | Revise proposal based on editorial direction |
| `elmer decline ID` | Discard branch and clean up |
| `elmer decline ID "reason"` | Decline with a reason (feeds digest synthesis) |
| `elmer digest` | Synthesize convergence digest from recent explorations |
| `elmer digest --since DATE` | Time-bounded digest |
| `elmer digest --topic KEYWORD` | Filtered digest |
| `elmer cancel ID` | Stop a running, pending, or amending exploration |
| `elmer retry ID` | Retry a failed exploration with same parameters |
| `elmer retry --failed` | Retry all failed explorations |
| `elmer costs` | Show cost summary for all explorations |
| `elmer validate` | Check document invariants |
| `elmer archetypes list` | List available archetypes |
| `elmer archetypes stats` | Show archetype effectiveness statistics |
| `elmer mine-questions` | Extract open questions from project docs |
| `elmer mine-questions --spawn` | Mine questions and explore them |
| `elmer insights` | List cross-project insights |
| `elmer implement "milestone"` | Decompose milestone into steps and execute autonomously |
| `elmer implement --dry-run` | Preview the plan without executing |
| `elmer implement --dry-run --save` | Save plan to `.elmer/plans/` for later review |
| `elmer implement --answers-file F` | Pre-answer decompose questions from JSON/TOML file |
| `elmer implement --load-plan F` | Load a saved plan JSON (skip decomposition) |
| `elmer implement --steps 0-3` | Run only specific steps (supports `0`, `0,2,5`, `0-3`) |
| `elmer implement --status` | Show active plan progress |
| `elmer implement --resume PLAN` | Resume a paused plan (retry failed steps) |
| `elmer daemon` | Start the daemon for continuous operation |
| `elmer daemon status` | Check if the daemon is running |
| `elmer daemon stop` | Gracefully stop the daemon |
| `elmer status -v` | Show topics for all explorations |
| `elmer status --all-projects` | Show status across all registered projects |
| `elmer logs ID` | Show parsed session log (diagnostics, errors, cost) |
| `elmer logs ID --raw` | Show raw JSON session log |
| `elmer pr ID` | Push branch and create GitHub PR |
| `elmer clean` | Remove finished worktrees and state entries |
| `elmer mcp` | Start the MCP server for Claude Code integration |

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
elmer explore "topic" --on-decline "elmer explore 'alternative to \$TOPIC'"  # Chain on declining
elmer explore "topic" --verify-cmd "pytest"    # Run verification before marking done (ADR-038)

# Ensemble exploration — run same topic N times, synthesize into one proposal
elmer explore "topic" --replicas 3                                   # 3 independent runs, auto-synthesize
elmer explore "topic" --replicas 3 --archetypes explore,devil-advocate,dead-end-analysis  # Different lenses
elmer explore "topic" --replicas 3 --models opus,sonnet,haiku        # Different models

# Decline with reasons (feeds digest synthesis)
elmer decline ID "too broad — focus on JWT validation only"
elmer decline ID "already addressed by exploration X"

# Review options
elmer review --prioritize              # Rank by blockers, staleness, diff size
elmer approve ID --validate-invariants # Check doc consistency after merge

# Digest — synthesize convergence across explorations
elmer digest                           # Synthesize all recent work
elmer digest --since "2026-02-01"      # Time-bounded
elmer digest --topic "auth"            # Filtered by keyword
elmer digest -m opus                   # Use opus for deeper synthesis

# Amend proposals before approving
elmer amend ID "Remove the Read-Aloud section"       # Revise proposal
elmer amend ID "Narrow scope to API layer" -m opus   # Use a specific model
elmer amend ID "Split into two proposals" --budget 1  # Cost-capped

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
elmer batch .elmer/explore-act.md --max-concurrent 3  # Only 3 run at once, rest queued
elmer batch .elmer/explore-act.md --stagger 5         # 5s delay between spawns
elmer batch .elmer/explore-act.md --replicas 3        # Ensemble: 3 replicas per topic

# Retry failed explorations
elmer retry my-exploration-id         # Retry one failed exploration
elmer retry --failed                  # Retry all failed explorations
elmer retry --failed --max-concurrent 3  # Throttled retry

# Multi-project
elmer status --all-projects            # Aggregated status across all projects

# Pull requests (requires gh CLI)
elmer pr my-exploration                # Push branch and create GitHub PR

# Implement — milestone decomposition and autonomous execution
elmer implement "Milestone 1a"              # Full flow: decompose -> clarify -> execute
elmer implement "Milestone 1a" --dry-run    # See the plan without executing
elmer implement "Milestone 1a" --dry-run --save  # Save plan for later
elmer implement "Milestone 1a" -y           # Skip clarifying questions
elmer implement "Milestone 1a" --answers-file answers.json  # Pre-answered questions
elmer implement --load-plan .elmer/plans/milestone-1a.json  # Load saved plan
elmer implement --load-plan plan.json --steps 0-2  # Run first 3 steps only
elmer implement --load-plan plan.json --steps 3,4  # Run specific steps
elmer implement "Milestone 1a" --budget 50  # $50 total across all steps
elmer implement "Milestone 1a" --max-concurrent 3  # Allow parallel steps
elmer implement --status                    # Show active plan progress
elmer implement --resume milestone-1a       # Resume after a paused step

# Daemon options
elmer daemon --interval 300            # 5-minute cycle interval
elmer daemon --auto-approve --generate # Full autonomy mode
elmer daemon --budget 5.00             # Cost cap per cycle
elmer daemon --max-concurrent 3        # Limit parallel explorations
elmer daemon --auto-followup           # Generate follow-ups after approvals
```

## Archetypes

Archetypes define how Claude explores a topic. Each archetype is implemented as a Claude Code custom subagent with tool restrictions and a methodology-specific system prompt (ADR-026).

| Archetype | Purpose | Tools |
|-----------|---------|-------|
| `explore` | Read-only analysis — think deeply, no action bias | Read, Grep, Glob, Bash, Write |
| `explore-act` | Analysis biased toward concrete action proposals | Read, Grep, Glob, Bash, Edit, Write |
| `prototype` | Write working code on the branch | Read, Grep, Glob, Bash, Edit, Write |
| `implement` | Implementation specialist with self-verification | Read, Grep, Glob, Bash, Edit, Write |
| `adr-proposal` | Propose architecture decisions with alternatives | Read, Grep, Glob, Bash, Edit, Write |
| `question-cluster` | Explore clusters of related open questions | Read, Grep, Glob, Bash, Write |
| `benchmark` | Measure, evaluate, and recommend improvements | Read, Grep, Glob, Bash, Edit, Write |
| `dead-end-analysis` | Analyze whether a direction is worth pursuing | Read, Grep, Glob, Bash, Write |
| `devil-advocate` | Challenge assumptions and decisions | Read, Grep, Glob, Bash, Write |

**Audit archetypes** use analysis tools (`Read, Grep, Glob, Bash, Write`): consistency-audit, coherence-audit, architecture-audit, documentation-audit, mission-audit, operational-audit, opportunity-scan, workflow-audit.

Use `--auto-archetype` to let AI pick the best archetype for each topic. Use `-a` to force a specific one.

Agent definitions are bundled with Elmer and used automatically. To customize, run `elmer init --agents` to scaffold local copies in `.claude/agents/`. Local copies override bundled defaults. Legacy `$TOPIC` template substitution (`.elmer/archetypes/`) is used as fallback when no agent definition exists. Use `elmer archetypes stats` to see which perform best.

To create a **new archetype** from scratch, you need both files: `.elmer/archetypes/<name>.md` (template fallback) and `.claude/agents/elmer-<name>.md` (agent definition). See GUIDE.md "Creating Custom Archetypes" for details.

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

[digest]
model = "sonnet"
max_turns = 5
threshold = 5            # Approvals since last digest before daemon auto-synthesizes

[verification]
# on_done = "make test"      # Global verification command for all explorations
# fallback = "make build"    # Fallback command when primary exhausts retries (ADR-040)
max_retries = 2              # Auto-amend attempts before marking failed
timeout = 300                # Verification timeout in seconds

[implement]
model = "opus"               # Model for implementation steps
decompose_model = "opus"     # Model for milestone decomposition
decompose_max_turns = 30     # Max turns for decomposition agent

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
.vscode/
└── settings.json      # Watcher exclusions for .elmer/ ephemeral dirs
```

With `--docs`, also creates in the project root:

```
CLAUDE.md              # Claude Code instructions
DESIGN.md              # Architecture and design
DECISIONS.md           # Architecture decision records
ROADMAP.md             # Phased development plan
CONTEXT.md             # Project context for AI assistants
```

With `--skills`, detects project characteristics and creates:

```
.claude/skills/
├── mission-align/SKILL.md    # If mission/principles detected
├── cultural-lens/SKILL.md    # If i18n/multilingual detected
├── persona-ux/SKILL.md       # If user personas detected
└── compliance-check/SKILL.md # If compliance requirements detected
```

These skills provide interactive analysis lenses (`/mission-align`, `/cultural-lens`, etc.) in Claude Code sessions, complementing Elmer's autonomous exploration archetypes.

With `--agents`, copies all bundled subagent definitions for customization:

```
.claude/agents/
├── elmer-explore-act.md       # Exploration agents (9)
├── elmer-explore.md
├── elmer-consistency-audit.md # Audit agents (8)
├── elmer-meta-review-gate.md  # Meta-operation agents (11)
├── elmer-meta-decompose.md    # Milestone decomposition
└── ...                        # 28 agents total
```

Agents define exploration methodology as Claude Code custom subagents with tool restrictions and model selection. Local copies override bundled defaults. See ADR-026 in DECISIONS.md.

## How Explorations Work

1. `elmer explore "topic"` creates a git worktree on branch `elmer/<slug>`
2. Resolves a Claude Code subagent for the archetype (or falls back to `$TOPIC` template)
3. Spawns `claude --agents <JSON> --agent <name> -p "<topic>"` in the worktree (background)
4. Claude reads project docs, investigates the topic, writes `PROPOSAL.md`
5. `elmer status` detects when the session finishes
6. `elmer review <id>` shows the proposal
7. `elmer approve <id>` merges the branch; `elmer decline <id>` discards it

## Using Elmer from Claude Code

### MCP Server (Recommended)

The MCP server exposes Elmer's state as structured JSON tools that Claude Code can call directly — no text parsing needed.

Add to your `.claude/mcp.json` (project-level) or `~/.claude/mcp.json` (global):

```json
{
  "mcpServers": {
    "elmer": {
      "command": "uv",
      "args": ["run", "elmer", "mcp"]
    }
  }
}
```

This gives Claude Code 23 tools in 5 categories, all returning structured JSON:

- **Read-only (8):** `elmer_status`, `elmer_review`, `elmer_costs`, `elmer_tree`, `elmer_archetypes`, `elmer_insights`, `elmer_config_get`, `elmer_recover_partial`
- **Mutation (8):** `elmer_explore`, `elmer_approve`, `elmer_amend`, `elmer_decline`, `elmer_cancel`, `elmer_retry`, `elmer_clean`, `elmer_pr`
- **Intelligence (4):** `elmer_generate`, `elmer_validate`, `elmer_mine_questions`, `elmer_digest`
- **Implementation (2):** `elmer_implement`, `elmer_plan_status`
- **Batch (1):** `elmer_batch`

### CLI Fallback

Elmer also works as a regular CLI tool from within Claude Code:

```bash
elmer explore "evaluate caching strategies"
elmer status
elmer review evaluate-caching-strategies
elmer approve evaluate-caching-strategies
```

Claude Code learns the commands from the project's `CLAUDE.md`. Note that `elmer explore` spawns a background `claude -p` process — nested Claude Code invocations work fine but be aware of cost and concurrency implications.

## Name

Elmer Fudd. Persistent hunter. Homage to the [Ralph Wiggum](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) naming tradition for autonomous Claude Code tools.
