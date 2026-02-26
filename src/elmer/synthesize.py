"""Ensemble synthesis — consolidate multiple proposals on the same topic.

When an ensemble's replicas all complete, this module reads their proposals,
runs the synthesis meta-agent, and creates a synthesis exploration that
enters the normal review queue.
"""

from pathlib import Path
from typing import Optional

from . import config, explore as explore_mod, state, worker, worktree


def synthesize_ensemble(
    *,
    ensemble_id: str,
    elmer_dir: Path,
    project_dir: Path,
    model: Optional[str] = None,
    max_turns: Optional[int] = None,
    previous_synthesis: Optional[str] = None,
) -> str:
    """Synthesize an ensemble's replica proposals into a single consolidated proposal.

    Reads PROPOSAL.md from all successful replicas, spawns the synthesis agent
    on a new branch, and creates a synthesis exploration. Returns the synthesis
    exploration slug.

    If previous_synthesis is provided (re-synthesis), it is included as context
    so the new synthesis agent can deepen rather than start from scratch.

    The synthesis exploration has ensemble_role='synthesis' and the same
    ensemble_id as the replicas.
    """
    if not worker.check_claude_available():
        raise RuntimeError(
            "claude CLI not found in PATH. Install Claude Code first."
        )

    conn = state.get_db(elmer_dir)

    # Verify no synthesis already exists
    existing = state.get_ensemble_synthesis(conn, ensemble_id)
    if existing is not None:
        conn.close()
        raise RuntimeError(
            f"Synthesis already exists for ensemble '{ensemble_id}': {existing['id']}"
        )

    # Read all successful replica proposals
    replicas = state.get_ensemble_replicas(conn, ensemble_id)
    if not replicas:
        conn.close()
        raise RuntimeError(f"No replicas found for ensemble '{ensemble_id}'.")

    done_replicas = [r for r in replicas if r["status"] == "done"]
    if not done_replicas:
        conn.close()
        raise RuntimeError(
            f"No successful replicas for ensemble '{ensemble_id}'. "
            f"All {len(replicas)} replica(s) failed."
        )

    # Collect proposals from replica worktrees
    proposals = []
    for i, replica in enumerate(done_replicas, 1):
        wt_path = Path(replica["worktree_path"])
        proposal_path = wt_path / "PROPOSAL.md"
        if proposal_path.exists():
            content = proposal_path.read_text()
            proposals.append(
                f"## Proposal {i} (ID: {replica['id']}, archetype: {replica['archetype']}, model: {replica['model']})\n\n"
                f"{content}"
            )

    if not proposals:
        conn.close()
        raise RuntimeError(
            f"No PROPOSAL.md files found in successful replica worktrees "
            f"for ensemble '{ensemble_id}'."
        )

    # Resolve config
    cfg = config.load_config(elmer_dir)
    ensemble_cfg = cfg.get("ensemble", {})
    defaults = cfg.get("defaults", {})

    use_model = model or ensemble_cfg.get("synthesis_model", defaults.get("model", "sonnet"))
    use_max_turns = max_turns or ensemble_cfg.get("synthesis_max_turns", 15)

    # Build the synthesis prompt
    topic = done_replicas[0]["topic"]
    proposals_text = "\n\n---\n\n".join(proposals)
    prompt = (
        f"Synthesize the following {len(proposals)} independent proposals on the topic:\n"
        f'"{topic}"\n\n'
        f"Each proposal was produced by an independent exploration with no knowledge of the others.\n\n"
        f"---\n\n{proposals_text}"
    )

    # Include previous synthesis for re-synthesis runs
    if previous_synthesis:
        prompt = (
            f"{prompt}\n\n"
            f"---\n\n"
            f"## Previous Synthesis (for deepening)\n\n"
            f"A previous synthesis was produced but was too shallow. "
            f"Use it as structural scaffolding — deepen the analysis, "
            f"challenge its conclusions against source documents, verify claims, "
            f"and fill gaps it left. Do not merely reproduce it.\n\n"
            f"{previous_synthesis}"
        )

    # Create synthesis branch and worktree
    synthesis_slug = f"{ensemble_id}-synthesis"
    branch = f"elmer/{synthesis_slug}"
    worktree_path = elmer_dir / "worktrees" / synthesis_slug
    log_path = elmer_dir / "logs" / f"{synthesis_slug}.log"

    if worktree.branch_exists(project_dir, branch):
        conn.close()
        raise RuntimeError(
            f"Branch '{branch}' already exists. "
            f"Use 'elmer clean' first."
        )

    # Resolve the synthesis agent
    agent_config = config.resolve_meta_agent(project_dir, "synthesize")

    if agent_config is not None:
        # Agent provides methodology via system prompt; prompt is just the data
        pass
    else:
        # No agent — prompt must be self-contained (already is)
        pass

    # Append PROPOSAL.md path directive
    abs_path = worktree_path.resolve()
    prompt = (
        f"{prompt}\n\n"
        f"IMPORTANT: Write your proposal to the absolute path: "
        f"{abs_path}/PROPOSAL.md — do not use a relative path."
    )

    worktree.create_worktree(project_dir, branch, worktree_path)

    pid = worker.spawn_claude(
        prompt=prompt,
        cwd=worktree_path,
        model=use_model,
        log_path=log_path,
        max_turns=use_max_turns,
        agent_config=agent_config,
    )

    state.create_exploration(
        conn,
        id=synthesis_slug,
        topic=f"[synthesis] {topic}",
        archetype="synthesize",
        branch=branch,
        worktree_path=str(worktree_path),
        model=use_model,
        pid=pid,
        max_turns=use_max_turns,
        ensemble_id=ensemble_id,
        ensemble_role="synthesis",
    )

    # Record synthesis cost as a meta-operation
    state.record_meta_cost(
        conn,
        operation="ensemble_synthesize",
        model=use_model,
        exploration_id=synthesis_slug,
    )

    conn.close()
    return synthesis_slug


def resynthesize_ensemble(
    *,
    ensemble_id: str,
    elmer_dir: Path,
    project_dir: Path,
    model: Optional[str] = None,
    max_turns: Optional[int] = None,
) -> str:
    """Re-trigger synthesis for an ensemble whose synthesis failed (E3).

    Deletes the failed synthesis exploration and re-runs synthesis.
    If the failed synthesis produced a partial PROPOSAL.md, it is passed
    as previous_synthesis context so the new attempt can build on it.
    """
    conn = state.get_db(elmer_dir)

    existing = state.get_ensemble_synthesis(conn, ensemble_id)
    if existing is None:
        conn.close()
        raise RuntimeError(
            f"No synthesis found for ensemble '{ensemble_id}'. "
            f"Use synthesize_ensemble() for first synthesis."
        )

    if existing["status"] not in ("failed", "done"):
        conn.close()
        raise RuntimeError(
            f"Synthesis for ensemble '{ensemble_id}' has status '{existing['status']}'. "
            f"Can only re-synthesize failed or done syntheses."
        )

    # Read partial output from failed synthesis if available
    previous_synthesis = None
    try:
        wt_path = Path(existing["worktree_path"])
        proposal_path = wt_path / "PROPOSAL.md"
        if proposal_path.exists():
            previous_synthesis = proposal_path.read_text()
    except Exception:
        pass

    # Clean up the failed synthesis
    synthesis_id = existing["id"]
    try:
        wt_path = Path(existing["worktree_path"])
        branch = existing["branch"]
        if wt_path.exists():
            worktree.remove_worktree(project_dir, wt_path)
        if worktree.branch_exists(project_dir, branch):
            worktree.delete_branch(project_dir, branch)
    except Exception:
        pass
    state.delete_exploration(conn, synthesis_id)
    conn.close()

    # Re-run synthesis with previous output as context
    return synthesize_ensemble(
        ensemble_id=ensemble_id,
        elmer_dir=elmer_dir,
        project_dir=project_dir,
        model=model,
        max_turns=max_turns,
        previous_synthesis=previous_synthesis,
    )


def get_failed_syntheses(elmer_dir: Path) -> list[str]:
    """Get ensemble IDs with failed synthesis explorations (E3).

    Used by the daemon to auto-detect and re-queue failed syntheses.
    """
    conn = state.get_db(elmer_dir)
    rows = conn.execute("""
        SELECT DISTINCT ensemble_id FROM explorations
        WHERE ensemble_role = 'synthesis' AND status = 'failed'
        AND ensemble_id IS NOT NULL
    """).fetchall()
    conn.close()
    return [r["ensemble_id"] for r in rows]


def trigger_ready_ensembles(
    elmer_dir: Path,
    project_dir: Path,
    *,
    model: Optional[str] = None,
    max_turns: Optional[int] = None,
    notify=None,
) -> list[str]:
    """Find ensembles ready for synthesis and trigger them.

    Returns list of synthesis slugs that were started.
    """
    if notify is None:
        import click
        notify = click.echo

    conn = state.get_db(elmer_dir)
    ready = state.get_ready_ensembles(conn)
    conn.close()

    synthesized = []
    for ensemble_id in ready:
        try:
            slug = synthesize_ensemble(
                ensemble_id=ensemble_id,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                model=model,
                max_turns=max_turns,
            )
            synthesized.append(slug)
            notify(f"Ensemble synthesis started: {slug}")
        except RuntimeError as e:
            notify(f"Ensemble synthesis failed for {ensemble_id}: {e}")

    # Re-trigger failed syntheses (E3)
    failed_ids = get_failed_syntheses(elmer_dir)
    for ensemble_id in failed_ids:
        try:
            slug = resynthesize_ensemble(
                ensemble_id=ensemble_id,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                model=model,
                max_turns=max_turns,
            )
            synthesized.append(slug)
            notify(f"Ensemble re-synthesis started: {slug}")
        except RuntimeError as e:
            notify(f"Ensemble re-synthesis failed for {ensemble_id}: {e}")

    return synthesized
