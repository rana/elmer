"""Elmer MCP Server — expose Elmer state and operations as structured MCP tools.

Read-only: status, review, costs, tree, archetypes, insights.
Mutation: explore, approve, amend, decline, cancel, retry, clean, pr.
Intelligence: generate, validate, mine_questions, digest.
Batch: batch (structured topic list).
Communicates via stdio JSON-RPC for Claude Code integration.
"""

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from . import (
    config,
    decompose as decompose_mod,
    digest as digest_mod,
    explore as explore_mod,
    gate,
    generate as gen_mod,
    implement as impl_mod,
    insights as insights_mod,
    invariants as inv_mod,
    plan as plan_mod,
    pr as pr_mod,
    questions as questions_mod,
    replan as replan_mod,
    state,
    worker,
    worktree as wt,
)

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
# Read-Only Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def elmer_status(status_filter: Optional[str] = None) -> dict:
    """List all explorations with their current state.

    Returns structured exploration data and a status summary.
    Use this to check what's running, what's done, and what needs review.

    For running and amending explorations, includes progress indicators:
    elapsed_minutes, pid_alive, and log_bytes.

    Optional status_filter: pending, running, done, approved, declined, failed.
    """
    try:
        _, elmer_dir = _find_project()
        conn = state.get_db(elmer_dir)
        explorations = state.list_explorations(conn, status=status_filter)

        result = []
        counts: dict[str, int] = {}
        now = datetime.now(timezone.utc)
        for exp in explorations:
            s = exp["status"]
            counts[s] = counts.get(s, 0) + 1
            entry = {
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
                "failure_category": exp["failure_category"] if s == "failed" else None,
            }

            # Progress indicators for active explorations
            if s in ("running", "amending"):
                try:
                    created = datetime.fromisoformat(exp["created_at"])
                    entry["elapsed_minutes"] = round(
                        (now - created).total_seconds() / 60, 1
                    )
                except (ValueError, TypeError):
                    pass
                entry["pid_alive"] = worker.is_running(exp["pid"])
                log_path = elmer_dir / "logs" / f"{exp['id']}.log"
                try:
                    entry["log_bytes"] = log_path.stat().st_size if log_path.exists() else 0
                except OSError:
                    entry["log_bytes"] = 0

            result.append(entry)

        conn.close()
        return {
            "explorations": result,
            "summary": {
                "running": counts.get("running", 0),
                "amending": counts.get("amending", 0),
                "done": counts.get("done", 0),
                "pending": counts.get("pending", 0),
                "approved": counts.get("approved", 0),
                "declined": counts.get("declined", 0),
                "failed": counts.get("failed", 0),
            },
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_review(
    exploration_id: Optional[str] = None,
    prioritize: bool = False,
) -> dict:
    """Review exploration proposals.

    Without exploration_id: lists all proposals pending review (status=done or failed).
    With exploration_id: returns full PROPOSAL.md content, metadata, and dependencies.
    With prioritize=true: ranks pending proposals by review priority (blockers,
    staleness, diff size). Use this to decide what to review next.
    """
    try:
        project_dir, elmer_dir = _find_project()
        conn = state.get_db(elmer_dir)

        # List mode: no specific exploration requested
        if exploration_id is None:
            done = state.list_explorations(conn, status="done")
            failed = state.list_explorations(conn, status="failed")
            proposals = list(done) + list(failed)

            if prioritize and proposals:
                scored = []
                for exp in proposals:
                    score, reasons = _score_proposal(exp, conn, project_dir)
                    scored.append({
                        "id": exp["id"],
                        "topic": exp["topic"],
                        "status": exp["status"],
                        "archetype": exp["archetype"],
                        "created_at": exp["created_at"],
                        "priority_score": score,
                        "priority_reasons": reasons,
                    })
                scored.sort(key=lambda x: -x["priority_score"])
                conn.close()
                return {"proposals": scored, "count": len(scored), "prioritized": True}

            result = [
                {
                    "id": exp["id"],
                    "topic": exp["topic"],
                    "status": exp["status"],
                    "archetype": exp["archetype"],
                    "created_at": exp["created_at"],
                    "failure_category": exp["failure_category"] if exp["status"] == "failed" else None,
                }
                for exp in proposals
            ]
            conn.close()
            return {"proposals": result, "count": len(result), "prioritized": False}

        # Detail mode: specific exploration
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

        # Read review notes if present (H3)
        review_notes_path = worktree_path / "REVIEW-NOTES.md"
        review_notes = None
        if review_notes_path.exists():
            review_notes = review_notes_path.read_text()

        return {
            "id": exp["id"],
            "topic": exp["topic"],
            "status": exp["status"],
            "proposal": proposal,
            "review_notes": review_notes,
            "archetype": exp["archetype"],
            "model": exp["model"],
            "branch": exp["branch"],
            "created_at": exp["created_at"],
            "completed_at": exp["completed_at"],
            "cost_usd": exp["cost_usd"],
            "input_tokens": exp["input_tokens"],
            "output_tokens": exp["output_tokens"],
            "num_turns_actual": exp["num_turns_actual"],
            "failure_category": exp["failure_category"] if exp["status"] == "failed" else None,
            "dependencies": dependencies,
            "dependents": dependents,
        }
    except Exception as exc:
        return {"error": str(exc)}


def _score_proposal(exp, conn, project_dir: Path) -> tuple[float, list[str]]:
    """Score a proposal for prioritized review. Returns (score, reasons).

    Higher score = review first. Scoring factors:
    - Blockers: is anything waiting on this? (+30 per dependent)
    - Staleness: older proposals get priority (+1 per hour, max 24)
    - Failed status: failed explorations need attention (+5)
    - Decision needed: proposals requiring decisions get priority (+15) (H2)
    - Low confidence: uncertain proposals need more scrutiny (+10) (H2)
    """
    from .review import parse_proposal_frontmatter

    score = 0.0
    reasons = []

    # Factor 1: Dependents — other explorations are blocked on this
    dependents = state.get_dependents(conn, exp["id"])
    if dependents:
        score += 30 * len(dependents)
        reasons.append(f"blocks {len(dependents)}")

    # Factor 2: Staleness — older proposals get priority
    try:
        created = datetime.fromisoformat(exp["created_at"])
        now = datetime.now(timezone.utc)
        hours = (now - created).total_seconds() / 3600
        staleness = min(hours, 24)
        score += staleness
        if hours > 12:
            reasons.append("stale")
    except (ValueError, TypeError):
        pass

    # Factor 3: Failed status — needs attention
    if exp["status"] == "failed":
        score += 5
        reasons.append("failed")

    # Factor 4+5: Frontmatter-based scoring (H2)
    try:
        worktree_path = Path(exp["worktree_path"])
        proposal_path = worktree_path / "PROPOSAL.md"
        if proposal_path.exists():
            meta, _ = parse_proposal_frontmatter(proposal_path.read_text())
            if meta.get("decision_needed") is True:
                score += 15
                reasons.append("decision needed")
            confidence = meta.get("confidence", "")
            if confidence == "low":
                score += 10
                reasons.append("low confidence")
            elif confidence == "medium":
                score += 5
    except Exception:
        pass  # Best-effort

    return score, reasons


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
    nested recursively. Use this to understand exploration relationships
    and find blocked work.
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
    Use this to choose an archetype before starting an exploration.
    """
    try:
        _, elmer_dir = _find_project()

        # Collect archetypes from both sources
        seen: dict[str, str] = {}  # name -> source

        # Bundled agent definitions
        for f in sorted(config.AGENTS_DIR.glob("*.md")):
            seen[f.stem] = "bundled"

        # Project-local agent definitions take precedence
        local_agents_dir = project_dir / ".claude" / "agents"
        if local_agents_dir.exists():
            for f in sorted(local_agents_dir.glob("elmer-*.md")):
                name = f.stem.removeprefix("elmer-")
                seen[name] = "project"

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
                declined = sum(1 for e in exps if e["status"] == "declined")
                decided = approved + declined
                costs = [e["cost_usd"] for e in exps if e["cost_usd"] is not None]
                stats_by_arch[arch] = {
                    "total": total,
                    "approved": approved,
                    "declined": declined,
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
def elmer_archetype_diagnose(archetype_name: str) -> dict:
    """Diagnose an archetype's effectiveness (I1).

    Analyzes approval/decline rates, decline reasons, verification failure
    counts, and topic patterns. Produces a structured diagnostic report
    useful for identifying systematic methodology issues.

    Parameters:
        archetype_name: The archetype to diagnose (e.g., "explore-act").
    """
    try:
        from . import archstats
        _, elmer_dir = _find_project()
        report = archstats.diagnose_archetype(elmer_dir, archetype_name)
        return report
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_insights(keywords: Optional[str] = None) -> dict:
    """Cross-project insights from the global insight log.

    Without keywords: returns all insights. With keywords: returns insights
    matching the keywords, ranked by relevance. Insights are generalizable
    findings extracted from approved explorations across all projects.
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


@mcp.tool()
def elmer_config_get(key: Optional[str] = None) -> dict:
    """Read Elmer configuration values.

    Returns the full config from .elmer/config.toml, or a specific key.
    Use dot notation for nested keys (e.g., "defaults.model",
    "auto_approve.criteria", "digest.threshold").

    Without key: returns the entire config dict.
    With key: returns just that value.

    Parameters:
        key: Dot-notation config key (e.g., "defaults.model"). Omit for full config.
    """
    try:
        _, elmer_dir = _find_project()
        cfg = config.load_config(elmer_dir)

        if key is None:
            return {"config": cfg}

        # Navigate nested dict via dot notation
        parts = key.split(".")
        current = cfg
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return {"key": key, "value": None, "found": False}
            current = current[part]

        return {"key": key, "value": current, "found": True}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_recover_partial(exploration_id: str) -> dict:
    """Recover partial artifacts from a failed exploration.

    Scans the exploration's worktree for markdown files that may contain
    useful partial work (drafts, analysis fragments, partial proposals).
    Only works if the worktree still exists (before cleanup).

    Returns file paths and content previews. Use this to salvage work
    from explorations that failed late (e.g., turn 48 of 50).

    Parameters:
        exploration_id: ID of the failed exploration.
    """
    try:
        _, elmer_dir = _find_project()
        conn = state.get_db(elmer_dir)
        exp = state.get_exploration(conn, exploration_id)
        conn.close()

        if exp is None:
            return {"error": f"Exploration '{exploration_id}' not found."}

        if exp["status"] not in ("failed", "done", "running", "amending"):
            return {"error": f"Recovery is for failed/active explorations, not '{exp['status']}'."}

        worktree_path = Path(exp["worktree_path"])
        if not worktree_path.exists():
            return {
                "error": "Worktree no longer exists. Run recovery before cleanup.",
                "exploration_id": exploration_id,
            }

        # Known project docs to exclude (not exploration artifacts)
        exclude = {
            "CLAUDE.md", "CONTEXT.md", "DESIGN.md", "DECISIONS.md",
            "ROADMAP.md", "README.md", "GUIDE.md", "CHANGELOG.md",
            "CONTRIBUTING.md", "LICENSE.md",
        }

        artifacts = []
        for md_file in sorted(worktree_path.rglob("*.md")):
            # Skip .elmer/ internals and known project docs
            try:
                rel = md_file.relative_to(worktree_path)
            except ValueError:
                continue
            if ".elmer" in rel.parts:
                continue
            if rel.name in exclude and len(rel.parts) == 1:
                continue

            try:
                content = md_file.read_text()
                preview = content[:1000]
                if len(content) > 1000:
                    preview += "\n\n[...truncated...]"
                artifacts.append({
                    "path": str(rel),
                    "size_bytes": len(content),
                    "preview": preview,
                })
            except OSError:
                continue

        return {
            "exploration_id": exploration_id,
            "status": exp["status"],
            "worktree": str(worktree_path),
            "artifacts": artifacts,
            "artifact_count": len(artifacts),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Mutation Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def elmer_explore(
    topic: str,
    archetype: Optional[str] = None,
    model: Optional[str] = None,
    max_turns: Optional[int] = None,
    auto_approve: bool = False,
    auto_archetype: bool = False,
    generate_prompt: bool = False,
    depends_on: Optional[str] = None,
    parent_id: Optional[str] = None,
    on_approve: Optional[str] = None,
    on_decline: Optional[str] = None,
    replicas: Optional[int] = None,
    archetypes: Optional[str] = None,
    models: Optional[str] = None,
) -> dict:
    """Start a new exploration on a git branch.

    Creates a git worktree, spawns a background Claude Code session to
    investigate the topic, and tracks it in Elmer's state. The session
    writes a PROPOSAL.md when done.

    Use after elmer_generate to spawn AI-generated topics, or directly
    for specific research questions.

    With replicas > 1, starts an ensemble: N independent explorations of
    the same topic that auto-synthesize into a single consolidated proposal.

    Parameters:
        topic: What to explore (required).
        archetype: Prompt template (default: from config). Overrides auto_archetype.
        model: Claude model — sonnet, opus, haiku (default: from config).
        max_turns: Turn limit for the claude session (default: from config).
        auto_approve: If true, AI reviews the proposal on completion.
        auto_archetype: If true, AI selects the best archetype for the topic.
        generate_prompt: If true, uses two-stage AI prompt generation.
        depends_on: Comma-separated exploration IDs this depends on.
        parent_id: Parent exploration ID (for follow-ups).
        on_approve: Shell command to run on approval ($ID, $TOPIC substituted).
        on_decline: Shell command to run on decline ($ID, $TOPIC substituted).
        replicas: Ensemble mode — spawn N replicas and auto-synthesize (min 2).
        archetypes: Ensemble — comma-separated archetype rotation per replica.
        models: Ensemble — comma-separated model rotation per replica.
    """
    try:
        project_dir, elmer_dir = _find_project()
        cfg = config.load_config(elmer_dir)
        defaults = cfg.get("defaults", {})

        # -a forces a specific archetype and disables auto-selection
        use_auto_archetype = auto_archetype and archetype is None
        use_archetype = archetype or defaults.get("archetype", "explore-act")
        use_model = model or defaults.get("model", "opus")
        use_max_turns = max_turns or defaults.get("max_turns", 50)

        # Resolve generate_prompt from config if not explicitly set
        use_generate = generate_prompt or defaults.get("generate_prompt", False)

        if replicas and replicas >= 2:
            # Ensemble mode
            archetype_list = [a.strip() for a in archetypes.split(",")] if archetypes else None
            model_list = [m.strip() for m in models.split(",")] if models else None

            results = explore_mod.start_ensemble(
                topic=topic,
                replicas=replicas,
                archetype=use_archetype,
                model=use_model,
                max_turns=use_max_turns,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                archetypes=archetype_list,
                models=model_list,
                auto_approve=auto_approve,
                generate_prompt=use_generate,
                auto_archetype=use_auto_archetype,
            )

            return {
                "mode": "ensemble",
                "replicas": [{"id": slug, "archetype": arch} for slug, arch in results],
                "replica_count": len(results),
                "topic": topic,
                "message": f"Ensemble started with {len(results)} replicas. Synthesis triggers automatically when all complete.",
            }

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
            auto_archetype=use_auto_archetype,
            generate_prompt=use_generate,
            depends_on=dep_list,
            parent_id=parent_id,
            on_approve=on_approve,
            on_decline=on_decline,
        )

        # Read actual status from DB (deps may already be approved -> running)
        conn = state.get_db(elmer_dir)
        exp = state.get_exploration(conn, slug)
        conn.close()
        actual_status = exp["status"] if exp else "unknown"

        return {
            "id": slug,
            "topic": topic,
            "branch": f"elmer/{slug}",
            "archetype": archetype_used,
            "model": use_model,
            "status": actual_status,
            "auto_archetype": use_auto_archetype,
            "generate_prompt": use_generate,
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_approve(
    exploration_id: Optional[str] = None,
    approve_all: bool = False,
    auto_followup: bool = False,
    followup_count: int = 3,
    validate_invariants: bool = False,
) -> dict:
    """Approve and merge an exploration.

    Merges the exploration's git branch into the current branch, cleans up
    the worktree, and marks the exploration as approved. If other explorations
    depend on this one, they will be unblocked and started.

    With approve_all=true: approves all explorations in 'done' status.
    With auto_followup=true: generates follow-up topics after approval.
    With validate_invariants=true: runs document consistency checks after merge.

    Parameters:
        exploration_id: ID of the exploration to approve (required unless approve_all).
        approve_all: Approve all pending proposals at once.
        auto_followup: Generate follow-up topics after approval.
        followup_count: Number of follow-up topics to generate (default: 3).
        validate_invariants: Run document invariant checks after merge.
    """
    try:
        project_dir, elmer_dir = _find_project()
        messages: list[str] = []

        if approve_all:
            try:
                approved = gate.approve_all(
                    elmer_dir, project_dir,
                    auto_followup=auto_followup,
                    followup_count=followup_count,
                )
            except SystemExit:
                return {"error": "Batch approval failed. Check for merge conflicts."}

            result: dict = {
                "approved": approved if approved else [],
                "count": len(approved) if approved else 0,
                "messages": messages,
            }

            if validate_invariants and approved:
                inv_result = _run_invariants(elmer_dir, project_dir)
                if inv_result is not None:
                    result["invariants"] = inv_result

            return result

        if not exploration_id:
            return {"error": "Provide exploration_id or set approve_all=true."}

        try:
            gate.approve_exploration(
                elmer_dir, project_dir, exploration_id,
                auto_followup=auto_followup,
                followup_count=followup_count,
                notify=messages.append,
            )
        except SystemExit:
            conn = state.get_db(elmer_dir)
            exp = state.get_exploration(conn, exploration_id)
            conn.close()
            if exp is None:
                return {"error": f"Exploration '{exploration_id}' not found."}
            if exp["status"] not in ("done", "failed"):
                return {"error": f"Cannot approve exploration in status '{exp['status']}'. Must be 'done' or 'failed'."}
            return {"error": f"Merge failed for '{exploration_id}'. Resolve conflicts manually."}

        result = {
            "approved": exploration_id,
            "messages": messages,
        }

        if validate_invariants:
            inv_result = _run_invariants(elmer_dir, project_dir)
            if inv_result is not None:
                result["invariants"] = inv_result

        return result
    except Exception as exc:
        return {"error": str(exc)}


def _run_invariants(elmer_dir: Path, project_dir: Path) -> Optional[dict]:
    """Run document invariant validation. Returns structured result or None on error."""
    try:
        cfg = config.load_config(elmer_dir)
        inv_cfg = cfg.get("invariants", {})
        inv_model = inv_cfg.get("model", "sonnet")
        inv_max_turns = inv_cfg.get("max_turns", 5)

        vr = inv_mod.validate_invariants(
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=inv_model,
            max_turns=inv_max_turns,
        )

        return {
            "all_passed": vr.all_passed,
            "checks": [
                {"invariant": c.invariant, "passed": c.passed, "detail": c.detail}
                for c in vr.checks
            ],
            "fixes": vr.fixes,
        }
    except Exception:
        return None


@mcp.tool()
def elmer_decline(exploration_id: str, reason: Optional[str] = None) -> dict:
    """Decline and discard an exploration.

    Deletes the exploration's git branch and worktree. The exploration is
    marked as declined. Log files are preserved. Cannot decline an
    already-approved exploration.

    If reason is provided, it is stored and feeds into digest synthesis
    and future topic generation.
    """
    try:
        project_dir, elmer_dir = _find_project()
        messages: list[str] = []

        try:
            gate.decline_exploration(
                elmer_dir, project_dir, exploration_id,
                reason=reason,
                notify=messages.append,
            )
        except SystemExit:
            conn = state.get_db(elmer_dir)
            exp = state.get_exploration(conn, exploration_id)
            conn.close()
            if exp is None:
                return {"error": f"Exploration '{exploration_id}' not found."}
            if exp["status"] == "approved":
                return {"error": "Cannot decline an already-approved exploration."}
            return {"error": f"Failed to decline '{exploration_id}'."}

        result = {
            "declined": exploration_id,
            "messages": messages,
        }
        if reason:
            result["reason"] = reason
        return result
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_amend(
    exploration_id: str,
    feedback: str,
    model: Optional[str] = None,
    max_turns: int = 10,
    dry_run: bool = False,
) -> dict:
    """Amend a completed exploration's proposal.

    Spawns a Claude session in the existing worktree to revise PROPOSAL.md
    based on editorial direction. The exploration transitions to 'amending'
    while the revision runs, then back to 'done' for re-review.

    Use this when a proposal needs changes before approval — removing sections,
    narrowing scope, fixing cross-references, or adjusting emphasis. The amend
    agent re-evaluates coherence after applying changes.

    Parameters:
        exploration_id: ID of the exploration to amend (must be done or failed).
        feedback: Editorial direction — what to change, remove, or adjust.
        model: Model for the amend session (default: same as original exploration).
        max_turns: Turn limit for the amend session (default: 10).
        dry_run: If true, returns the assembled prompt without spawning
            a session. Use this to review what the amend agent would receive.
    """
    try:
        project_dir, elmer_dir = _find_project()

        if dry_run:
            preview = explore_mod.preview_amend_prompt(
                exploration_id=exploration_id,
                feedback=feedback,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
            )
            return {
                "id": exploration_id,
                "dry_run": True,
                "prompt": preview["prompt"],
                "agent": preview["agent"],
                "model": model or preview["model"],
            }

        pid = explore_mod.amend_exploration(
            exploration_id=exploration_id,
            feedback=feedback,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=model,
            max_turns=max_turns,
        )

        return {
            "id": exploration_id,
            "status": "amending",
            "pid": pid,
            "feedback": feedback[:200],
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_cancel(exploration_id: str) -> dict:
    """Cancel a running, pending, or amending exploration.

    Stops the Claude session (if running/amending), removes the worktree and branch,
    and marks the exploration as failed (retryable). Log files are preserved.

    The exploration must be in 'running', 'pending', or 'amending' status.
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
            if exp["status"] not in ("running", "pending", "amending"):
                return {"error": f"Cannot cancel exploration in status '{exp['status']}'. Must be 'running', 'pending', or 'amending'."}
            return {"error": f"Failed to cancel '{exploration_id}'."}

        return {
            "cancelled": exploration_id,
            "messages": messages,
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_retry(
    exploration_id: Optional[str] = None,
    retry_all_failed: bool = False,
    max_concurrent: Optional[int] = None,
) -> dict:
    """Retry failed explorations or re-run a completed synthesis.

    Re-spawns a failed exploration with the same topic, archetype, and model.
    The old failed entry is cleaned up and a new exploration is created.

    For completed synthesis explorations: archives the previous synthesis
    and re-runs with the current archetype. The previous synthesis is passed
    as context so the new agent can deepen rather than start from scratch.

    With retry_all_failed=true: retries all explorations in 'failed' status.

    Parameters:
        exploration_id: ID of the exploration to retry (failed or done synthesis).
        retry_all_failed: Retry all failed explorations at once.
        max_concurrent: Max parallel retries (excess queued as pending).
    """
    try:
        project_dir, elmer_dir = _find_project()

        if not exploration_id and not retry_all_failed:
            return {"error": "Provide exploration_id or set retry_all_failed=true."}

        if exploration_id and retry_all_failed:
            return {"error": "Cannot combine a specific ID with retry_all_failed."}

        if retry_all_failed:
            new_slugs = gate.retry_all_failed(
                elmer_dir, project_dir, max_concurrent=max_concurrent,
            )
            return {
                "retried": new_slugs,
                "count": len(new_slugs),
            }

        new_slug = gate.retry_exploration(elmer_dir, project_dir, exploration_id)
        return {"retried": new_slug}

    except (SystemExit, RuntimeError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_clean(preview: bool = False) -> dict:
    """Clean up finished explorations.

    Removes worktrees and state entries for approved, declined, and failed
    explorations. Running and pending explorations are not affected.
    Use this periodically to free disk space and declutter status output.

    Parameters:
        preview: If true, returns what would be cleaned without executing.
            Shows exploration IDs, statuses, topics, and whether worktrees
            still exist. Use this to inspect before committing to cleanup.
    """
    try:
        project_dir, elmer_dir = _find_project()
        if preview:
            items = gate.clean_preview(elmer_dir)
            return {
                "preview": True,
                "would_clean": len(items),
                "items": items,
            }
        count = gate.clean_all(elmer_dir, project_dir)
        return {"cleaned": count}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_pr(exploration_id: str) -> dict:
    """Create a GitHub PR from an exploration.

    Pushes the exploration branch to the remote and creates a PR using
    the gh CLI. The PROPOSAL.md content becomes the PR body.

    Requires the gh CLI (https://cli.github.com/) in PATH.
    The exploration must have a branch (status: done, failed, or running).
    """
    try:
        project_dir, elmer_dir = _find_project()

        try:
            pr_url = pr_mod.create_pr_for_exploration(
                elmer_dir, project_dir, exploration_id,
            )
        except SystemExit:
            conn = state.get_db(elmer_dir)
            exp = state.get_exploration(conn, exploration_id)
            conn.close()
            if exp is None:
                return {"error": f"Exploration '{exploration_id}' not found."}
            return {"error": f"Cannot create PR for exploration in status '{exp['status']}'."}

        return {"pr_url": pr_url, "exploration_id": exploration_id}
    except RuntimeError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Intelligence Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def elmer_generate(
    count: Optional[int] = None,
    follow_up_id: Optional[str] = None,
    model: Optional[str] = None,
    spawn: bool = True,
    archetype: Optional[str] = None,
    auto_approve: bool = False,
    auto_archetype: bool = False,
) -> dict:
    """Generate research topics using AI and optionally spawn explorations.

    Reads project documentation and exploration history to propose topics
    worth exploring. This is the main way to discover what to research next.

    With spawn=true (default): generates topics AND starts explorations.
    With spawn=false: generates topics only (dry run).
    With follow_up_id: generates follow-up topics for a completed exploration.

    Parameters:
        count: Number of topics to generate (default: 5).
        follow_up_id: Generate follow-ups for this completed exploration.
        model: Model for topic generation (default: from config, usually sonnet).
        spawn: If true, spawns explorations from generated topics (default: true).
        archetype: Archetype for spawned explorations (default: from config).
        auto_approve: Auto-approve spawned explorations via AI review.
        auto_archetype: AI selects the best archetype per spawned topic.
    """
    try:
        project_dir, elmer_dir = _find_project()
        cfg = config.load_config(elmer_dir)
        gen_cfg = cfg.get("generate", {})
        defaults = cfg.get("defaults", {})

        gen_model = model or gen_cfg.get("model", defaults.get("model", "sonnet"))
        gen_count = count or gen_cfg.get("count", 5)
        gen_max_turns = gen_cfg.get("max_turns", 5)

        # Capture digest metadata before generation (best-effort)
        digest_context = None
        try:
            digests_dir = elmer_dir / "digests"
            if digests_dir.exists():
                digest_files = sorted(digests_dir.glob("digest-*.md"), reverse=True)
                if digest_files:
                    latest = digest_files[0]
                    mtime = datetime.fromtimestamp(
                        latest.stat().st_mtime, tz=timezone.utc
                    )
                    age_hours = (
                        datetime.now(timezone.utc) - mtime
                    ).total_seconds() / 3600
                    digest_context = {
                        "path": str(latest.relative_to(elmer_dir)),
                        "timestamp": mtime.isoformat(),
                        "age_hours": round(age_hours, 1),
                    }
        except Exception:
            pass  # Best-effort — never block generation

        topics = gen_mod.generate_topics(
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            count=gen_count,
            follow_up_id=follow_up_id,
            model=gen_model,
            max_turns=gen_max_turns,
        )

        result: dict = {"topics": topics, "count": len(topics)}
        if digest_context:
            result["digest_used"] = digest_context

        if not spawn:
            result["spawned"] = False
            return result

        # Spawn explorations from generated topics
        use_auto_archetype = auto_archetype and archetype is None
        explore_archetype = archetype or defaults.get("archetype", "explore-act")
        explore_model = defaults.get("model", "sonnet")
        explore_max_turns = defaults.get("max_turns", 50)

        spawned = []
        errors = []
        for topic in topics:
            try:
                slug, archetype_used = explore_mod.start_exploration(
                    topic=topic,
                    archetype=explore_archetype,
                    model=explore_model,
                    max_turns=explore_max_turns,
                    elmer_dir=elmer_dir,
                    project_dir=project_dir,
                    parent_id=follow_up_id,
                    auto_approve=auto_approve,
                    auto_archetype=use_auto_archetype,
                )
                spawned.append({"id": slug, "archetype": archetype_used})
            except (RuntimeError, FileNotFoundError) as e:
                errors.append({"topic": topic, "error": str(e)})

        result["spawned"] = True
        result["explorations"] = spawned
        if errors:
            result["errors"] = errors

        return result
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_validate(model: Optional[str] = None, preview: bool = False) -> dict:
    """Validate document invariants.

    Checks that project documentation is internally consistent. Default rules
    check ADR counts, phase status, and feature claims. Auto-fixes mechanical
    violations (counts, status labels).

    Use after approving explorations that modify project documents, or
    periodically to catch documentation drift.

    Parameters:
        model: Model for validation (default: sonnet).
        preview: If true, reports violations without applying fixes.
            The validation agent runs in check-only mode with write tools
            removed. Use this to inspect what would be fixed first.
    """
    try:
        project_dir, elmer_dir = _find_project()
        cfg = config.load_config(elmer_dir)
        inv_cfg = cfg.get("invariants", {})
        inv_model = model or inv_cfg.get("model", "sonnet")
        inv_max_turns = inv_cfg.get("max_turns", 5)

        # State invariants: fast deterministic checks (no AI)
        conn = state.get_db(elmer_dir)
        state_violations = state.check_state_invariants(conn)
        conn.close()

        vr = inv_mod.validate_invariants(
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=inv_model,
            max_turns=inv_max_turns,
            preview=preview,
        )

        result = {
            "all_passed": vr.all_passed and not state_violations,
            "state_violations": state_violations,
            "checks": [
                {"invariant": c.invariant, "passed": c.passed, "detail": c.detail}
                for c in vr.checks
            ],
            "fixes": vr.fixes,
            "cost_usd": vr.cost_usd,
        }
        if preview:
            result["preview"] = True
        return result
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_digest(
    model: Optional[str] = None,
    since: Optional[str] = None,
    topic_filter: Optional[str] = None,
) -> dict:
    """Synthesize a convergence digest from recent explorations.

    Reads approved proposals, declined proposals with reasons, and the
    exploration history to produce a synthesis document. The digest identifies
    convergence themes, contradictions, gaps, decline patterns, and
    recommended directions.

    Digests feed into topic generation (the generate tool reads the latest
    digest automatically) and the daemon loop (auto-triggered when approvals
    accumulate past the configured threshold).

    Optional filters:
    - since: ISO date string — only include explorations after this date
    - topic_filter: keyword — only include explorations matching this keyword
    """
    try:
        project_dir, elmer_dir = _find_project()
        cfg = config.load_config(elmer_dir)
        d_cfg = cfg.get("digest", {})
        digest_model = model or d_cfg.get("model", "sonnet")

        digest_path = digest_mod.run_digest(
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=digest_model,
            max_turns=d_cfg.get("max_turns", 5),
            since=since,
            topic_filter=topic_filter,
        )

        # Read the digest content for the response
        content = digest_path.read_text()
        if content.startswith("<!--"):
            try:
                end = content.index("-->")
                content = content[end + 3:].strip()
            except ValueError:
                pass

        return {
            "digest_path": str(digest_path),
            "content": content,
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_mine_questions(
    model: Optional[str] = None,
    cluster_filter: Optional[str] = None,
    spawn: bool = False,
    max_per_cluster: int = 3,
    archetype: Optional[str] = None,
    auto_approve: bool = False,
) -> dict:
    """Extract open questions from project documentation.

    Parses CONTEXT.md, DESIGN.md, ROADMAP.md, DECISIONS.md for explicit
    questions and implicit gaps. Groups them by theme.

    Use this to discover what the project's documentation doesn't yet answer.
    With spawn=true, converts questions to explorations automatically.

    Parameters:
        model: Model for question mining (default: from config).
        cluster_filter: Only return questions from clusters matching this name.
        spawn: If true, converts questions to explorations (default: false).
        max_per_cluster: Max questions per cluster to spawn (default: 3).
        archetype: Archetype for spawned explorations (default: from config).
        auto_approve: Auto-approve spawned explorations via AI review.
    """
    try:
        project_dir, elmer_dir = _find_project()
        cfg = config.load_config(elmer_dir)
        q_cfg = cfg.get("questions", {})
        defaults = cfg.get("defaults", {})
        q_model = model or q_cfg.get("model", defaults.get("model", "opus"))

        clusters = questions_mod.mine_questions(
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=q_model,
            max_turns=q_cfg.get("max_turns", 5),
        )

        # Apply cluster filter for display
        filtered: dict[str, list[str]] = {}
        for name, questions in clusters.items():
            if cluster_filter and cluster_filter.lower() not in name.lower():
                continue
            filtered[name] = questions

        total_questions = sum(len(qs) for qs in filtered.values())
        result: dict = {
            "clusters": filtered,
            "total_questions": total_questions,
            "cluster_count": len(filtered),
        }

        if not spawn:
            return result

        # Convert to topics and spawn
        topics = questions_mod.clusters_to_topics(
            clusters,
            cluster_filter=cluster_filter,
            max_per_cluster=max_per_cluster,
        )

        if not topics:
            result["spawned"] = []
            return result

        explore_archetype = archetype or defaults.get("archetype", "explore-act")
        explore_model = defaults.get("model", "opus")
        explore_max_turns = defaults.get("max_turns", 50)

        spawned = []
        errors = []
        for topic in topics:
            try:
                slug, archetype_used = explore_mod.start_exploration(
                    topic=topic,
                    archetype=explore_archetype,
                    model=explore_model,
                    max_turns=explore_max_turns,
                    elmer_dir=elmer_dir,
                    project_dir=project_dir,
                    auto_approve=auto_approve,
                )
                spawned.append({"id": slug, "archetype": archetype_used})
            except (RuntimeError, FileNotFoundError) as e:
                errors.append({"topic": topic, "error": str(e)})

        result["spawned"] = spawned
        if errors:
            result["errors"] = errors

        return result
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Batch Tool
# ---------------------------------------------------------------------------


@mcp.tool()
def elmer_batch(
    topics: str,
    archetype: Optional[str] = None,
    model: Optional[str] = None,
    max_turns: Optional[int] = None,
    chain: bool = False,
    auto_approve: bool = False,
    auto_archetype: bool = False,
    max_concurrent: Optional[int] = None,
    stagger_seconds: Optional[int] = None,
    replicas: Optional[int] = None,
    archetypes: Optional[str] = None,
    models: Optional[str] = None,
) -> dict:
    """Run multiple explorations from a list of topics.

    Structured alternative to the CLI 'elmer batch' command. Takes a
    newline-separated list of topics instead of a file path.

    With chain=true: topics run sequentially, each depending on the previous.
    This prevents merge conflicts when topics touch overlapping files.

    With max_concurrent: limits parallel explorations. Excess are queued
    and launch as running ones complete.

    With replicas: each topic becomes an ensemble with N replicas that
    auto-synthesize into a single proposal.

    Parameters:
        topics: Newline-separated list of topics to explore (required).
        archetype: Archetype for all explorations (default: from config).
        model: Claude model (default: from config).
        max_turns: Turn limit per exploration (default: from config).
        chain: Run topics sequentially, each depending on the previous.
        auto_approve: Auto-approve via AI review when done.
        auto_archetype: AI selects the best archetype per topic.
        max_concurrent: Max parallel explorations.
        stagger_seconds: Delay in seconds between spawning each exploration.
            Spreads out concurrent starts to avoid API rate limits.
        replicas: Ensemble — spawn N replicas per topic and auto-synthesize.
        archetypes: Ensemble — comma-separated archetype rotation per replica.
        models: Ensemble — comma-separated model rotation per replica.
    """
    try:
        project_dir, elmer_dir = _find_project()
        cfg = config.load_config(elmer_dir)
        defaults = cfg.get("defaults", {})

        topic_list = [t.strip() for t in topics.strip().split("\n") if t.strip()]
        if not topic_list:
            return {"error": "No topics provided."}

        use_auto_archetype = auto_archetype and archetype is None
        use_archetype = archetype or defaults.get("archetype", "explore-act")
        use_model = model or defaults.get("model", "sonnet")
        use_max_turns = max_turns or defaults.get("max_turns", 50)

        spawned_slugs: list[str] = []
        spawned: list[dict] = []
        errors: list[dict] = []
        previous_slug = None

        archetype_list = [a.strip() for a in archetypes.split(",")] if archetypes else None
        model_list = [m.strip() for m in models.split(",")] if models else None

        for i, topic in enumerate(topic_list):
            dep_list = None
            if chain and previous_slug is not None:
                dep_list = [previous_slug]
            elif max_concurrent is not None and i >= max_concurrent:
                dep_list = [spawned_slugs[i - max_concurrent]]

            try:
                if replicas and replicas >= 2:
                    # Ensemble mode
                    results = explore_mod.start_ensemble(
                        topic=topic,
                        replicas=replicas,
                        archetype=use_archetype,
                        model=use_model,
                        max_turns=use_max_turns,
                        elmer_dir=elmer_dir,
                        project_dir=project_dir,
                        archetypes=archetype_list,
                        models=model_list,
                        auto_approve=auto_approve,
                        generate_prompt=False,
                        auto_archetype=use_auto_archetype,
                    )
                    for slug, arch_used in results:
                        spawned_slugs.append(slug)
                    spawned.append({
                        "topic": topic,
                        "mode": "ensemble",
                        "replicas": [{"id": s, "archetype": a} for s, a in results],
                    })
                    previous_slug = results[-1][0] if results else previous_slug
                else:
                    slug, archetype_used = explore_mod.start_exploration(
                        topic=topic,
                        archetype=use_archetype,
                        model=use_model,
                        max_turns=use_max_turns,
                        elmer_dir=elmer_dir,
                        project_dir=project_dir,
                        depends_on=dep_list,
                        auto_approve=auto_approve,
                        auto_archetype=use_auto_archetype,
                    )
                    spawned_slugs.append(slug)
                    spawned.append({
                        "id": slug,
                        "topic": topic,
                        "archetype": archetype_used,
                        "depends_on": dep_list,
                    })
                    previous_slug = slug
            except (RuntimeError, FileNotFoundError) as e:
                errors.append({"topic": topic, "error": str(e)})
                if chain:
                    errors.append({"topic": "(chain broken)", "error": "Stopped due to previous error."})
                    break

            # Stagger: delay between spawns to avoid API rate limits
            if stagger_seconds and i < len(topic_list) - 1:
                time.sleep(stagger_seconds)

        result: dict = {
            "total_topics": len(topic_list),
            "spawned": spawned,
            "spawned_count": len(spawned),
            "chain": chain,
            "ensemble": bool(replicas and replicas >= 2),
        }
        if errors:
            result["errors"] = errors
        if max_concurrent is not None:
            launched = min(max_concurrent, len(spawned))
            result["launched_immediately"] = launched
            result["queued"] = len(spawned) - launched

        return result
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Implementation Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def elmer_implement(
    milestone: str,
    dry_run: bool = False,
    skip_clarify: bool = False,
    model: Optional[str] = None,
    max_concurrent: int = 1,
    from_exploration: Optional[str] = None,
) -> dict:
    """Decompose a milestone into implementation steps and execute autonomously.

    Reads project docs (ROADMAP.md, DESIGN.md, DECISIONS.md), decomposes
    the milestone into ordered steps with verification commands, and
    executes them as chained explorations with auto-amend on failure.

    Parameters:
        milestone: Milestone reference (e.g., "Milestone 1a").
        dry_run: Decompose and return plan without executing.
        skip_clarify: Skip clarification questions (use defaults).
        model: Model for implementation sessions (default: from config).
        max_concurrent: Max parallel steps (default: 1 for chain safety).
        from_exploration: Feed an exploration's PROPOSAL.md into decomposition (A4).
    """
    try:
        project_dir, elmer_dir = _find_project()

        # Decompose
        plan = decompose_mod.decompose_milestone(
            milestone_ref=milestone,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=model,
            from_exploration=from_exploration,
        )

        if dry_run:
            return {
                "milestone": plan.get("milestone", milestone),
                "steps": [
                    {
                        "index": i,
                        "title": s.get("title", ""),
                        "verify_cmd": s.get("verify_cmd", ""),
                        "depends_on": s.get("depends_on", []),
                    }
                    for i, s in enumerate(plan.get("steps", []))
                ],
                "questions": plan.get("questions", []),
                "dry_run": True,
            }

        # Execute
        plan_id = impl_mod.execute_plan(
            plan=plan,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=model,
            auto_approve=True,
            max_concurrent=max_concurrent,
        )

        return {
            "plan_id": plan_id,
            "milestone": plan.get("milestone", milestone),
            "steps_created": len(plan.get("steps", [])),
            "questions_skipped": len(plan.get("questions", [])) if skip_clarify else 0,
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_plan_status(plan_id: Optional[str] = None) -> dict:
    """Show status of implementation plans with per-step progress.

    Parameters:
        plan_id: Specific plan to query (default: all plans).
    """
    try:
        _, elmer_dir = _find_project()
        plans = plan_mod.get_plan_status(elmer_dir, plan_id)

        return {
            "plans": [
                {
                    "id": p["id"],
                    "milestone": p["milestone_ref"],
                    "status": p["status"],
                    "total_cost": p.get("total_cost", 0),
                    "steps": p.get("steps", []),
                    "revision_count": p.get("revision_count") or 0,
                    "replan_trigger_step": p.get("replan_trigger_step"),
                }
                for p in plans
            ]
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def elmer_replan(
    plan_id: str,
    failure_context: str = "",
    dry_run: bool = False,
    model: Optional[str] = None,
) -> dict:
    """Revise a paused plan when step failure reveals a structural problem.

    When a step fails because the plan itself is wrong (not just the
    implementation), replan invokes a meta-agent that produces a revised
    plan. Approved steps are preserved; failed/pending steps are remapped
    or replaced.

    Parameters:
        plan_id: The plan to revise.
        failure_context: Explanation of why the plan is structurally wrong.
            If empty, auto-extracts from the failed step's logs.
        dry_run: Preview the revised plan without applying it.
        model: Model for the replan agent (default: opus).
    """
    try:
        project_dir, elmer_dir = _find_project()

        if not failure_context:
            # Auto-extract failure context
            conn = state.get_db(elmer_dir)
            plan_exps = state.get_plan_explorations(conn, plan_id)
            conn.close()

            failed_exps = [
                e for e in plan_exps
                if e["status"] == "failed"
                and not (e.get("proposal_summary") or "").startswith("(dependency failed:")
            ]
            parts = []
            for exp in failed_exps:
                parts.append(
                    f"Step {exp['plan_step']} ({exp['id']}) failed: "
                    f"{exp.get('proposal_summary', '(no summary)')}"
                )
            failure_context = "\n".join(parts) if parts else "Step failure (no details available)"

        result = replan_mod.replan(
            plan_id=plan_id,
            failure_context=failure_context,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=model,
            dry_run=dry_run,
        )

        if dry_run:
            return {
                "status": "dry_run",
                "revised_plan": {
                    "milestone": result.get("milestone", ""),
                    "revision_note": result.get("revision_note", ""),
                    "steps": [
                        {
                            "index": i,
                            "title": s.get("title", ""),
                            "preserved_from": s.get("preserved_from"),
                        }
                        for i, s in enumerate(result.get("steps", []))
                    ],
                    "step_mapping": result.get("step_mapping", {}),
                },
            }

        return {
            "status": "revised",
            "plan_id": plan_id,
            "preserved": result.get("preserved", 0),
            "remapped": result.get("remapped", 0),
            "created": result.get("created", 0),
            "cancelled": result.get("cancelled", 0),
            "total_new_steps": result.get("total_new_steps", 0),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Run the MCP server on stdio transport."""
    mcp.run(transport="stdio")
