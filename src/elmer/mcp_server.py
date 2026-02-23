"""Elmer MCP Server — expose Elmer state as structured MCP tools.

Phase 1 (read-only): status, review, costs, tree, archetypes, insights.
Phase 2 (mutation): explore, approve, reject, cancel.
Communicates via stdio JSON-RPC for Claude Code integration.
"""

import json
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from . import config, explore as explore_mod, gate, insights as insights_mod, state, worktree as wt

mcp = FastMCP("elmer")


def _find_project() -> tuple[Path, Path]:
    """Find project root and .elmer/ directory from cwd."""
    project_dir = wt.get_project_root()
    elmer_dir = project_dir / ".elmer"
    if not elmer_dir.exists():
        raise RuntimeError(".elmer/ not found. Run 'elmer init' first.")
    return project_dir, elmer_dir


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def elmer_status(status: Optional[str] = None) -> dict:
    """List all explorations with their current state.

    Returns structured exploration data and a status summary.
    Optional status filter: pending, running, done, approved, rejected, failed.
    """
    try:
        _, elmer_dir = _find_project()
        conn = state.get_db(elmer_dir)
        explorations = state.list_explorations(conn, status=status)

        result = []
        counts: dict[str, int] = {}
        for exp in explorations:
            s = exp["status"]
            counts[s] = counts.get(s, 0) + 1
            result.append({
                "id": exp["id"],
                "topic": exp["topic"],
                "archetype": exp["archetype"],
                "status": s,
                "model": exp["model"],
                "branch": exp["branch"],
                "created_at": exp["created_at"],
                "completed_at": exp["completed_at"],
                "cost_usd": exp["cost_usd"],
                "parent_id": exp["parent_id"],
                "has_proposal": exp["proposal_summary"] is not None,
            })

        conn.close()
        return {
            "explorations": result,
            "summary": {
                "running": counts.get("running", 0),
                "done": counts.get("done", 0),
                "pending": counts.get("pending", 0),
                "approved": counts.get("approved", 0),
                "rejected": counts.get("rejected", 0),
                "failed": counts.get("failed", 0),
            },
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_review(exploration_id: str) -> dict:
    """Read a proposal with full metadata.

    Returns the PROPOSAL.md content, exploration metadata, and dependency info.
    """
    try:
        _, elmer_dir = _find_project()
        conn = state.get_db(elmer_dir)
        exp = state.get_exploration(conn, exploration_id)

        if exp is None:
            conn.close()
            return {"error": f"Exploration '{exploration_id}' not found."}

        # Read proposal content
        worktree_path = Path(exp["worktree_path"])
        proposal_path = worktree_path / "PROPOSAL.md"
        if proposal_path.exists():
            proposal = proposal_path.read_text()
        else:
            proposal = None

        dependencies = state.get_dependencies(conn, exploration_id)
        dependents = state.get_dependents(conn, exploration_id)
        conn.close()

        return {
            "id": exp["id"],
            "topic": exp["topic"],
            "status": exp["status"],
            "proposal": proposal,
            "archetype": exp["archetype"],
            "model": exp["model"],
            "branch": exp["branch"],
            "created_at": exp["created_at"],
            "completed_at": exp["completed_at"],
            "cost_usd": exp["cost_usd"],
            "input_tokens": exp["input_tokens"],
            "output_tokens": exp["output_tokens"],
            "num_turns_actual": exp["num_turns_actual"],
            "dependencies": dependencies,
            "dependents": dependents,
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_costs(exploration_id: Optional[str] = None) -> dict:
    """Cost summary for explorations and meta-operations.

    Without exploration_id: returns all exploration costs, meta-operation costs,
    and totals. With exploration_id: returns costs for that single exploration.
    """
    try:
        _, elmer_dir = _find_project()
        conn = state.get_db(elmer_dir)

        if exploration_id:
            exp = state.get_exploration(conn, exploration_id)
            if exp is None:
                conn.close()
                return {"error": f"Exploration '{exploration_id}' not found."}

            # Linked meta-operations
            meta_rows = conn.execute(
                "SELECT * FROM costs WHERE exploration_id = ? ORDER BY created_at",
                (exploration_id,),
            ).fetchall()
            conn.close()

            meta_ops = [
                {
                    "operation": mc["operation"],
                    "model": mc["model"],
                    "input_tokens": mc["input_tokens"],
                    "output_tokens": mc["output_tokens"],
                    "cost_usd": mc["cost_usd"],
                }
                for mc in meta_rows
            ]

            return {
                "exploration": {
                    "id": exp["id"],
                    "model": exp["model"],
                    "status": exp["status"],
                    "input_tokens": exp["input_tokens"],
                    "output_tokens": exp["output_tokens"],
                    "cost_usd": exp["cost_usd"],
                    "num_turns_actual": exp["num_turns_actual"],
                    "budget_usd": exp["budget_usd"],
                },
                "meta_operations": meta_ops,
            }

        # Summary for all explorations
        explorations = state.list_explorations(conn)
        meta_costs = state.get_all_costs(conn)
        conn.close()

        exp_list = [
            {
                "id": e["id"],
                "cost_usd": e["cost_usd"],
                "input_tokens": e["input_tokens"],
                "output_tokens": e["output_tokens"],
                "status": e["status"],
                "model": e["model"],
            }
            for e in explorations
            if e["cost_usd"] is not None
        ]

        # Group meta-operations by (operation, model)
        groups: dict[tuple[str, str], list] = {}
        for mc in meta_costs:
            key = (mc["operation"], mc["model"])
            groups.setdefault(key, []).append(mc)

        meta_list = []
        total_meta = 0.0
        for (op, model), items in sorted(groups.items()):
            group_cost = sum(m["cost_usd"] or 0.0 for m in items)
            total_meta += group_cost
            meta_list.append({
                "operation": op,
                "model": model,
                "count": len(items),
                "cost_usd": round(group_cost, 4),
            })

        total_exp = sum(e["cost_usd"] or 0.0 for e in exp_list)

        return {
            "explorations": exp_list,
            "meta_operations": meta_list,
            "total_cost_usd": round(total_exp + total_meta, 4),
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_tree() -> dict:
    """Dependency tree of explorations as structured data.

    Returns a tree with root explorations and their children (dependents),
    nested recursively.
    """
    try:
        _, elmer_dir = _find_project()
        conn = state.get_db(elmer_dir)
        explorations = state.list_explorations(conn)

        # Build lookup and find which explorations have parents (dependencies)
        by_id = {e["id"]: e for e in explorations}
        children_of: dict[str, list[str]] = {}  # parent_id -> [child_ids]
        has_parent: set[str] = set()

        for exp in explorations:
            deps = state.get_dependencies(conn, exp["id"])
            for dep_id in deps:
                children_of.setdefault(dep_id, []).append(exp["id"])
                has_parent.add(exp["id"])

        conn.close()

        def _build_node(eid: str, visited: set[str]) -> dict:
            if eid in visited:
                return {"id": eid, "status": "circular-ref", "children": []}
            visited.add(eid)
            exp = by_id.get(eid)
            node = {
                "id": eid,
                "status": exp["status"] if exp else "unknown",
                "topic": exp["topic"] if exp else None,
                "children": [],
            }
            for child_id in children_of.get(eid, []):
                node["children"].append(_build_node(child_id, visited))
            return node

        # Roots are explorations with no dependencies
        roots = [e["id"] for e in explorations if e["id"] not in has_parent]
        tree = [_build_node(rid, set()) for rid in roots]

        return {"roots": tree}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_archetypes(include_stats: bool = False) -> dict:
    """List available archetypes with optional effectiveness stats.

    Lists both bundled and project-local archetypes. When include_stats is true,
    includes approval rates and cost data computed from exploration history.
    """
    try:
        _, elmer_dir = _find_project()

        # Collect archetypes from both sources
        seen: dict[str, str] = {}  # name -> source

        # Project-local archetypes take precedence
        local_dir = elmer_dir / "archetypes"
        if local_dir.exists():
            for f in sorted(local_dir.glob("*.md")):
                seen[f.stem] = "project"

        # Bundled archetypes
        for f in sorted(config.ARCHETYPES_DIR.glob("*.md")):
            if f.stem not in seen:
                seen[f.stem] = "bundled"

        result = []
        stats_by_arch: dict[str, dict] = {}

        if include_stats:
            conn = state.get_db(elmer_dir)
            explorations = state.list_explorations(conn)
            conn.close()

            # Group by archetype and compute stats
            by_arch: dict[str, list] = {}
            for exp in explorations:
                by_arch.setdefault(exp["archetype"], []).append(exp)

            for arch, exps in by_arch.items():
                total = len(exps)
                approved = sum(1 for e in exps if e["status"] == "approved")
                rejected = sum(1 for e in exps if e["status"] == "rejected")
                decided = approved + rejected
                costs = [e["cost_usd"] for e in exps if e["cost_usd"] is not None]
                stats_by_arch[arch] = {
                    "total": total,
                    "approved": approved,
                    "rejected": rejected,
                    "approval_rate": round(approved / decided, 2) if decided > 0 else None,
                    "avg_cost_usd": round(sum(costs) / len(costs), 4) if costs else None,
                }

        for name in sorted(seen):
            entry: dict = {"name": name, "source": seen[name]}
            if include_stats:
                entry["stats"] = stats_by_arch.get(name)
            result.append(entry)

        return {"archetypes": result}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_insights(keywords: Optional[str] = None) -> dict:
    """Cross-project insights from the global insight log.

    Without keywords: returns all insights. With keywords: returns insights
    matching the keywords, ranked by relevance.
    """
    try:
        if keywords:
            insights = insights_mod.get_relevant_insights(keywords)
            return {
                "insights": [
                    {
                        "text": ins["text"],
                        "source_project": ins.get("source_project"),
                        "source_exploration": ins.get("source_exploration"),
                        "source_topic": ins.get("source_topic"),
                    }
                    for ins in insights
                ],
            }

        rows = insights_mod.list_all_insights()
        return {
            "insights": [
                {
                    "id": row["id"],
                    "text": row["text"],
                    "source_project": row["source_project"],
                    "source_exploration": row["source_exploration"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Phase 2 — Mutation Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def elmer_explore(
    topic: str,
    archetype: Optional[str] = None,
    model: Optional[str] = None,
    max_turns: Optional[int] = None,
    auto_approve: bool = False,
    budget_usd: Optional[float] = None,
    depends_on: Optional[str] = None,
) -> dict:
    """Start a new exploration on a git branch.

    Creates a git worktree, spawns a background Claude Code session to
    investigate the topic, and tracks it in Elmer's state. The session
    writes a PROPOSAL.md when done.

    Requires the claude CLI in PATH. This spawns a real background process.

    Parameters:
        topic: What to explore (required).
        archetype: Prompt template to use (default: from config, usually explore-act).
        model: Claude model (default: from config, usually opus).
        max_turns: Turn limit for the claude session (default: from config, usually 50).
        auto_approve: If true, AI reviews the proposal when done.
        budget_usd: Cost cap in USD for the claude session.
        depends_on: Comma-separated exploration IDs this depends on.
    """
    try:
        project_dir, elmer_dir = _find_project()
        cfg = config.load_config(elmer_dir)
        defaults = cfg.get("defaults", {})

        use_archetype = archetype or defaults.get("archetype", "explore-act")
        use_model = model or defaults.get("model", "opus")
        use_max_turns = max_turns or defaults.get("max_turns", 50)

        dep_list = None
        if depends_on:
            dep_list = [d.strip() for d in depends_on.split(",") if d.strip()]

        slug, archetype_used = explore_mod.start_exploration(
            topic=topic,
            archetype=use_archetype,
            model=use_model,
            max_turns=use_max_turns,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            auto_approve=auto_approve,
            budget_usd=budget_usd,
            depends_on=dep_list,
        )

        # Read actual status from DB (deps may already be approved → running)
        conn = state.get_db(elmer_dir)
        exp = state.get_exploration(conn, slug)
        conn.close()
        actual_status = exp["status"] if exp else "unknown"

        return {
            "id": slug,
            "branch": f"elmer/{slug}",
            "archetype": archetype_used,
            "model": use_model,
            "status": actual_status,
            "budget_usd": budget_usd,
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_approve(exploration_id: str) -> dict:
    """Approve and merge an exploration.

    Merges the exploration's git branch into the current branch, cleans up
    the worktree, and marks the exploration as approved. If other explorations
    depend on this one, they will be unblocked and started.

    The exploration must be in 'done' or 'failed' status.
    """
    try:
        project_dir, elmer_dir = _find_project()
        messages: list[str] = []

        try:
            gate.approve_exploration(
                elmer_dir, project_dir, exploration_id,
                notify=messages.append,
            )
        except SystemExit:
            # gate.py uses sys.exit(1) for validation errors — the last
            # click.echo(err=True) call has the error message. Collect
            # what we can from the state.
            conn = state.get_db(elmer_dir)
            exp = state.get_exploration(conn, exploration_id)
            conn.close()
            if exp is None:
                return {"error": f"Exploration '{exploration_id}' not found."}
            if exp["status"] not in ("done", "failed"):
                return {"error": f"Cannot approve exploration in status '{exp['status']}'. Must be 'done' or 'failed'."}
            return {"error": f"Merge failed for '{exploration_id}'. Resolve conflicts manually."}

        return {
            "approved": exploration_id,
            "messages": messages,
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_reject(exploration_id: str) -> dict:
    """Reject and discard an exploration.

    Deletes the exploration's git branch and worktree. The exploration is
    marked as rejected. Log files are preserved. Cannot reject an
    already-approved exploration.
    """
    try:
        project_dir, elmer_dir = _find_project()
        messages: list[str] = []

        try:
            gate.reject_exploration(
                elmer_dir, project_dir, exploration_id,
                notify=messages.append,
            )
        except SystemExit:
            conn = state.get_db(elmer_dir)
            exp = state.get_exploration(conn, exploration_id)
            conn.close()
            if exp is None:
                return {"error": f"Exploration '{exploration_id}' not found."}
            if exp["status"] == "approved":
                return {"error": "Cannot reject an already-approved exploration."}
            return {"error": f"Failed to reject '{exploration_id}'."}

        return {
            "rejected": exploration_id,
            "messages": messages,
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_cancel(exploration_id: str) -> dict:
    """Cancel a running or pending exploration.

    Stops the Claude session (if running), removes the worktree and branch,
    and marks the exploration as rejected. Log files are preserved.

    The exploration must be in 'running' or 'pending' status.
    """
    try:
        project_dir, elmer_dir = _find_project()
        messages: list[str] = []

        try:
            gate.cancel_exploration(
                elmer_dir, project_dir, exploration_id,
                notify=messages.append,
            )
        except SystemExit:
            conn = state.get_db(elmer_dir)
            exp = state.get_exploration(conn, exploration_id)
            conn.close()
            if exp is None:
                return {"error": f"Exploration '{exploration_id}' not found."}
            if exp["status"] not in ("running", "pending"):
                return {"error": f"Cannot cancel exploration in status '{exp['status']}'. Must be 'running' or 'pending'."}
            return {"error": f"Failed to cancel '{exploration_id}'."}

        return {
            "cancelled": exploration_id,
            "messages": messages,
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Run the MCP server on stdio transport."""
    mcp.run(transport="stdio")
