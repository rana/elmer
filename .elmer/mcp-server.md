# Implement Elmer MCP Server (Phase 1 — Read-Only)

Read CLAUDE.md, DESIGN.md, DECISIONS.md, and README.md first to ground in the project's actual state. Then read src/elmer/state.py, src/elmer/cli.py, src/elmer/review.py, src/elmer/costs.py, src/elmer/insights.py, and src/elmer/config.py to understand the query functions you'll wrap.

## What to Build

An MCP (Model Context Protocol) server that exposes Elmer's state and operations as structured tools, callable by Claude Code or any MCP client. This replaces the lossy CLI-via-Bash pattern (formatted tables parsed as text) with structured JSON responses.

The server communicates via stdio JSON-RPC, the standard transport for Claude Code MCP servers.

## Architecture

Create `src/elmer/mcp_server.py` (not `mcp.py` — avoid shadowing the `mcp` package). Add `elmer mcp` CLI subcommand that starts the server.

The MCP server wraps existing module functions. No new execution model, no new state management. The server is a presentation layer over `state.py`, `review.py`, `costs.py`, `insights.py`, and `config.py`.

## Dependencies

Add `mcp>=1.0` to the `dependencies` list in `pyproject.toml`. The `mcp` package is Anthropic's official Python SDK for MCP servers.

Use `from mcp.server import Server` and the `@server.tool()` decorator pattern. Use `mcp.server.stdio` for the stdio transport. Check the `mcp` package's actual API — import names may vary slightly by version. Adapt to what's actually installed.

## MCP Tools to Implement (Phase 1 — Read-Only)

### elmer_status

List all explorations with their current state. Returns structured JSON instead of a formatted table.

```json
{
  "explorations": [
    {
      "id": "evaluate-caching",
      "topic": "evaluate caching strategies",
      "archetype": "explore-act",
      "status": "done",
      "model": "opus",
      "branch": "elmer/evaluate-caching",
      "created_at": "2026-02-23T10:00:00Z",
      "completed_at": "2026-02-23T10:15:00Z",
      "cost_usd": 1.23,
      "parent_id": null,
      "has_proposal": true
    }
  ],
  "summary": {
    "running": 1,
    "done": 3,
    "pending": 2,
    "approved": 10,
    "rejected": 4,
    "failed": 1
  }
}
```

Parameters: optional `status` filter (string).

### elmer_review

Read a proposal. Returns the PROPOSAL.md content plus metadata.

```json
{
  "id": "evaluate-caching",
  "topic": "evaluate caching strategies",
  "status": "done",
  "proposal": "Full PROPOSAL.md content here...",
  "archetype": "explore-act",
  "model": "opus",
  "cost_usd": 1.23,
  "dependencies": ["prior-analysis"],
  "dependents": ["follow-up-caching"]
}
```

Parameters: `exploration_id` (required string).

### elmer_costs

Cost summary. Returns structured cost data instead of a formatted table.

```json
{
  "explorations": [
    {"id": "evaluate-caching", "cost_usd": 1.23, "input_tokens": 50000, "output_tokens": 8000}
  ],
  "meta_operations": [
    {"operation": "generate", "model": "sonnet", "cost_usd": 0.05}
  ],
  "total_cost_usd": 5.67
}
```

Parameters: optional `exploration_id` (string).

### elmer_tree

Dependency tree as structured data.

```json
{
  "roots": [
    {
      "id": "evaluate-caching",
      "status": "approved",
      "children": [
        {"id": "follow-up-redis", "status": "done", "children": []},
        {"id": "follow-up-memcached", "status": "running", "children": []}
      ]
    }
  ]
}
```

Parameters: none.

### elmer_archetypes

List available archetypes with optional stats.

```json
{
  "archetypes": [
    {
      "name": "explore-act",
      "source": "bundled",
      "stats": {"total": 15, "approved": 10, "rejected": 3, "approval_rate": 0.77}
    }
  ]
}
```

Parameters: optional `include_stats` (boolean, default false).

### elmer_insights

Cross-project insights.

```json
{
  "insights": [
    {
      "id": 1,
      "text": "Keyword-based search is sufficient for v1 cross-project features",
      "source_project": "elmer",
      "source_exploration": "evaluate-search",
      "created_at": "2026-02-20T..."
    }
  ]
}
```

Parameters: optional `keywords` (string) for filtering.

## Implementation Pattern

```python
"""Elmer MCP Server — expose Elmer state as MCP tools."""

import json
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
# ... adapt imports to actual mcp package API

from . import config, costs as costs_mod, insights as insights_mod, state, worktree as wt


def _find_project() -> tuple[Path, Path]:
    """Find project root and .elmer/ directory."""
    project_dir = wt.get_project_root()
    elmer_dir = project_dir / ".elmer"
    if not elmer_dir.exists():
        raise RuntimeError(".elmer/ not found. Run 'elmer init' first.")
    return project_dir, elmer_dir


server = Server("elmer")

# Register tools with @server.tool() or equivalent API
# Each tool wraps existing module functions
# Return structured JSON, not formatted text

# ... implement tools ...

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
```

The exact API may differ from this sketch. Read the `mcp` package source or docs to get the correct decorator and transport patterns. Adapt as needed — the sketch shows intent, not exact syntax.

## CLI Command

Add to `cli.py`:

```python
@cli.command()
def mcp():
    """Start the MCP server for Claude Code integration.

    Exposes Elmer state as structured MCP tools. Configure in
    Claude Code via .claude/mcp.json or user settings.
    """
    from .mcp_server import main
    import asyncio
    asyncio.run(main())
```

## Project Detection

The MCP server needs to find the current project. Since it runs via stdio (started by Claude Code in the project directory), use `os.getcwd()` as the starting point for `wt.get_project_root()`. This is the same pattern the CLI uses.

If the server is started from outside a git repo, tools should return clear error messages rather than crashing.

## Error Handling

Tools should never crash the server. Wrap each tool's logic in try/except and return structured error responses:

```json
{"error": "Exploration 'nonexistent' not found."}
```

## What NOT to Build (Phase 1)

- No mutation tools (explore, approve, reject) — Phase 2.
- No MCP Resources — tools are sufficient for now.
- No MCP Prompts.
- No authentication or authorization.
- No tests beyond basic smoke tests — get the integration working first.

## Documentation Updates

After implementation:

1. **DESIGN.md**: Add MCP Server section under Architecture (new module, tool list, transport).
2. **DECISIONS.md**: Add ADR-024 for MCP server decision (rationale: structured data over CLI text parsing, bidirectional integration with Claude Code, existing modules already cleanly separated for wrapping).
3. **ROADMAP.md**: Move "MCP server" from Deferred to a new "Phase 5: Integration" or update the deferred note to say "Phase 1 implemented."
4. **README.md**: Add MCP section with setup instructions (how to configure in `.claude/mcp.json`).
5. **CLAUDE.md**: Update module table, ADR count.

ADR-024 rationale points:
- Elmer's modules are already cleanly separated (state, review, costs, insights) — wrapping is straightforward.
- CLI returns formatted text that Claude Code must parse; MCP returns structured JSON that Claude Code reasons about natively.
- The `mcp` Python SDK handles protocol details (JSON-RPC, stdio transport, tool registration).
- Read-only Phase 1 is zero-risk — it doesn't change Elmer's state or behavior.
- Phase 2 (mutation tools) can add explore, approve, reject behind confirmation flows.
- Alternative considered: REST API (adds web framework dependency, requires port management, conflicts with Elmer's no-web-framework constraint).

## Verification

After implementation, verify:
1. `uv run elmer mcp` starts without error (and waits for stdio input)
2. The MCP server responds to the `initialize` handshake
3. `tools/list` returns all implemented tools
4. Each tool returns valid JSON when called with correct parameters
5. Each tool returns a clear error when called with bad parameters
6. The server doesn't crash on any tool invocation

## Guiding Principles

- Wrap existing functions. Don't reimplement query logic.
- Return the data the modules already provide, structured as JSON.
- Keep the server stateless between tool calls — open/close DB connections per call, same as CLI commands do.
- Follow the existing code style (type hints, docstrings, import conventions).
- The MCP server is a new module in the existing package, not a separate package.
