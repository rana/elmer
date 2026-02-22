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

# Start explorations
elmer explore "evaluate COT positioning as 6th data axis"
elmer explore "prototype hybrid search API" -a prototype -m opus

# Check progress
elmer status

# Review proposals
elmer review                          # list pending
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
| `elmer explore "topic"` | Start an exploration on a new branch |
| `elmer explore -f topics.txt` | Batch explore from a file (one topic per line) |
| `elmer status` | Show all explorations and their states |
| `elmer review` | List proposals pending review |
| `elmer review ID` | Show a full proposal |
| `elmer approve ID` | Merge exploration branch and clean up |
| `elmer approve --all` | Approve all pending proposals |
| `elmer reject ID` | Discard branch and clean up |
| `elmer clean` | Remove finished worktrees and state entries |

## Options

```bash
elmer explore "topic" -a prototype    # Use prototype archetype (default: explore-act)
elmer explore "topic" -m opus         # Use opus model (default: sonnet)
elmer explore "topic" --max-turns 100 # Increase turn limit (default: 50)
```

## Archetypes

Archetypes are prompt templates that shape how Claude explores a topic.

| Archetype | Purpose |
|-----------|---------|
| `explore` | Read-only analysis — think deeply, no action bias |
| `explore-act` | Analysis biased toward concrete action proposals |
| `prototype` | Write working code on the branch |

Archetypes live in `.elmer/archetypes/`. Add your own by creating a markdown file with `$TOPIC` as the placeholder.

## Configuration

`.elmer/config.toml`:

```toml
[defaults]
archetype = "explore-act"
model = "sonnet"
max_turns = 50
```

## Prerequisites

- Git repository
- [Claude Code](https://claude.ai/claude-code) CLI (`claude` in PATH)
- Project should have appropriate tool permissions configured in `.claude/settings.json`

## Project Structure

When you run `elmer init`, it creates:

```
.elmer/
├── config.toml        # Configuration (committed)
├── archetypes/        # Prompt templates (committed)
│   ├── explore.md
│   ├── explore-act.md
│   └── prototype.md
├── worktrees/         # Git worktrees (gitignored)
├── logs/              # Claude session logs (gitignored)
└── state.db           # SQLite state (gitignored)
```

## How Explorations Work

1. `elmer explore "topic"` creates a git worktree on branch `elmer/<slug>`
2. Loads the archetype template, substitutes `$TOPIC`
3. Spawns `claude -p "<prompt>"` in the worktree directory (background)
4. Claude reads project docs, investigates the topic, writes `PROPOSAL.md`
5. `elmer status` detects when the session finishes
6. `elmer review <id>` shows the proposal
7. `elmer approve <id>` merges the branch; `elmer reject <id>` discards it

## Name

Elmer Fudd. Persistent hunter. Homage to the [Ralph Wiggum](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) naming tradition for autonomous Claude Code tools.
