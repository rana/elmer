# Elmer

Autonomous research with branching.

*"Be vewy vewy quiet, I'm hunting insights."*

Elmer creates git branches, spawns Claude Code sessions to explore topics autonomously, and queues proposals for your review. Approve to merge. Decline to discard. Let it run overnight.

## How It Works

```
topic → git worktree → claude -p → PROPOSAL.md → human review → merge or discard
```

Each exploration gets its own git branch and worktree. A background Claude Code session (`claude -p`) runs against the worktree, reads the project's documentation, investigates the topic, and writes a PROPOSAL.md. You review proposals and approve or decline them.

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

# Start an exploration
elmer explore "evaluate COT positioning as 6th data axis"

# Check progress
elmer status

# Review and decide
elmer review evaluate-cot-positioning
elmer approve evaluate-cot-positioning

# Clean up
elmer clean
```

## Capabilities

### Explore

Start investigations on isolated branches. Each gets its own git worktree and Claude Code session.

```bash
elmer explore "should we use WebSockets or SSE for real-time updates"
elmer explore "prototype the export CLI" -a prototype -m opus
elmer explore "challenge our microservices decision" -a devil-advocate
```

### Review & Decide

Review proposals, approve to merge, decline with reasons that feed future synthesis.

```bash
elmer review --prioritize
elmer approve my-exploration --auto-followup
elmer decline my-exploration "too broad — focus on JWT only"
elmer amend my-exploration "Remove the Read-Aloud section"
```

### Batch & Automate

Run topic lists from `---`-separated markdown files. Chain for sequential work. Run the daemon for overnight autonomy.

```bash
elmer batch .elmer/prototype.md --chain
elmer daemon --auto-approve --generate
```

### Implement

Decompose a milestone into ordered steps with dependency tracking and execute autonomously. Each step becomes an exploration with cross-step context injection.

```bash
elmer implement "Add user authentication with JWT"
elmer implement --status
elmer replan my-plan "The API needs gRPC not REST"
```

### Synthesize

Converge understanding across explorations. Generate new topics from gaps. Mine questions from documentation.

```bash
elmer digest
elmer generate --follow-up
elmer mine-questions --spawn
```

### Ensemble

Run the same topic through multiple independent lenses and synthesize into one consolidated proposal.

```bash
elmer explore "auth architecture" --replicas 3 \
  --archetypes explore,devil-advocate,dead-end-analysis
```

### Operate

Track status, costs, and dependencies. Works across multiple projects.

```bash
elmer status --all-projects
elmer costs
elmer tree
elmer logs my-exploration
elmer pr my-exploration
```

## Archetypes

Archetypes define how Claude explores a topic. Each is a Claude Code custom subagent with tool restrictions and a methodology-specific system prompt (ADR-026).

| Archetype | Purpose |
|-----------|---------|
| `explore` | Read-only analysis — think deeply, no action bias |
| `explore-act` | Analysis biased toward concrete action proposals (default) |
| `prototype` | Write working code on the branch |
| `implement` | Implementation specialist with self-verification |
| `adr-proposal` | Propose architecture decisions with alternatives |
| `question-cluster` | Explore clusters of related open questions |
| `benchmark` | Measure, evaluate, and recommend improvements |
| `dead-end-analysis` | Analyze whether a direction is worth pursuing |
| `devil-advocate` | Challenge assumptions and decisions |

**Audit archetypes** (read-only analysis): consistency-audit, coherence-audit, architecture-audit, documentation-audit, mission-audit, operational-audit, opportunity-scan, workflow-audit.

Use `-a` to select an archetype. Use `--auto-archetype` to let AI choose. See GUIDE.md for the archetype decision tree and custom archetype creation.

Agent definitions are bundled with Elmer. To customize, run `elmer init --agents` to scaffold local copies in `.claude/agents/`. Local copies override bundled defaults.

## Prerequisites

- Git repository
- [Claude Code](https://claude.ai/claude-code) CLI (`claude` in PATH)
- Tool permissions configured in `.claude/settings.json`
- [GitHub CLI](https://cli.github.com/) (`gh`) — optional, for `elmer pr`

## Documentation

| Document | Contents |
|----------|----------|
| **[GUIDE.md](GUIDE.md)** | Practitioner's playbook — workflows, command reference, configuration, MCP server, troubleshooting, patterns |
| **[CONTEXT.md](CONTEXT.md)** | Project methodology, AI collaboration model, current state, open questions |
| **[DESIGN.md](DESIGN.md)** | Architecture, modules, data model, state machine, MCP server tools |
| **[DECISIONS.md](DECISIONS.md)** | 59 architecture decision records with rationale |
| **[ROADMAP.md](ROADMAP.md)** | Phase history and 12 remaining future directions |

## Name

Elmer Fudd. Persistent hunter. Homage to the [Ralph Wiggum](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) naming tradition for autonomous Claude Code tools.

*Last updated: 2026-02-26, restructure — product overview; command reference and configuration moved to GUIDE.md*
