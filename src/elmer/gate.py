"""Approval gate — approve (merge) or reject (discard) explorations."""

import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from . import config, explore as explore_mod, generate as gen_mod, insights, state, worktree


def _cleanup_worktree(project_dir: Path, exp: dict) -> None:
    """Remove worktree and branch for an exploration."""
    worktree_path = Path(exp["worktree_path"])
    branch = exp["branch"]

    if worktree_path.exists():
        try:
            worktree.remove_worktree(project_dir, worktree_path)
        except subprocess.CalledProcessError:
            # Worktree may already be gone; force remove the directory
            import shutil
            shutil.rmtree(worktree_path, ignore_errors=True)
            # Prune worktree list
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=str(project_dir),
                capture_output=True,
            )

    try:
        worktree.delete_branch(project_dir, branch)
    except subprocess.CalledProcessError:
        pass  # Branch may already be gone


def _execute_chain_action(
    action: str,
    exploration_id: str,
    topic: str,
    project_dir: Path,
    notify=None,
) -> None:
    """Execute a chain action command with $ID and $TOPIC substitution."""
    if notify is None:
        notify = click.echo
    cmd = action.replace("$ID", exploration_id).replace("$TOPIC", topic)
    notify(f"Chain action: {cmd}")
    try:
        subprocess.run(
            shlex.split(cmd),
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        notify(f"Chain action failed: {e}")


def approve_exploration(
    elmer_dir: Path,
    project_dir: Path,
    exploration_id: str,
    *,
    auto_followup: bool = False,
    followup_count: int = 3,
    followup_model: Optional[str] = None,
    followup_auto_approve: bool = False,
    notify=None,
) -> None:
    """Approve an exploration: merge its branch and clean up.

    If auto_followup is True, generates follow-up topics and spawns
    them as new explorations after the merge.
    """
    if notify is None:
        notify = click.echo

    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)

    if exp is None:
        click.echo(f"Exploration '{exploration_id}' not found.", err=True)
        sys.exit(1)

    if exp["status"] not in ("done", "failed"):
        click.echo(
            f"Cannot approve exploration in status '{exp['status']}'. "
            f"Must be 'done' or 'failed'.",
            err=True,
        )
        sys.exit(1)

    # Merge branch
    branch = exp["branch"]
    try:
        worktree.merge_branch(
            project_dir,
            branch,
            f"Merge elmer exploration: {exp['topic']}",
        )
    except subprocess.CalledProcessError as e:
        click.echo(f"Merge failed (conflicts?):\n{e.stderr}", err=True)
        click.echo(
            f"Resolve manually, then run: elmer approve {exploration_id}",
            err=True,
        )
        sys.exit(1)

    # Extract cross-project insights before cleanup (needs worktree for PROPOSAL.md)
    cfg = config.load_config(elmer_dir)
    ins_cfg = cfg.get("insights", {})
    if ins_cfg.get("enabled", False):
        try:
            extracted = insights.extract_insights(
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                exploration_id=exploration_id,
                model=ins_cfg.get("model", "sonnet"),
                max_turns=ins_cfg.get("max_turns", 3),
            )
            for ins in extracted:
                notify(f"Insight: {ins}")
        except Exception as e:
            notify(f"Insight extraction failed: {e}")

    # Cleanup
    _cleanup_worktree(project_dir, exp)

    state.update_exploration(
        conn,
        exploration_id,
        status="approved",
        merged_at=datetime.now(timezone.utc).isoformat(),
    )
    conn.close()

    # Schedule any pending explorations that were waiting on this one
    launched = explore_mod.schedule_ready(elmer_dir, project_dir)
    for slug in launched:
        notify(f"Unblocked and started: {slug}")

    # Execute on_approve chain action
    on_approve = exp["on_approve"] if "on_approve" in exp.keys() else None
    if on_approve:
        _execute_chain_action(
            on_approve, exploration_id, exp["topic"], project_dir, notify=notify,
        )

    # Generate follow-up topics
    if auto_followup:
        try:
            cfg = config.load_config(elmer_dir)
            fu_cfg = cfg.get("followup", {})
            fu_model = followup_model or fu_cfg.get("model", "sonnet")

            topics = gen_mod.generate_topics(
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                count=followup_count,
                follow_up_id=exploration_id,
                model=fu_model,
            )
            defaults = cfg.get("defaults", {})
            for topic in topics:
                slug, _ = explore_mod.start_exploration(
                    topic=topic,
                    archetype=exp["archetype"],
                    model=exp["model"],
                    max_turns=exp["max_turns"] or defaults.get("max_turns", 50),
                    elmer_dir=elmer_dir,
                    project_dir=project_dir,
                    parent_id=exploration_id,
                    auto_approve=followup_auto_approve,
                )
                notify(f"Follow-up started: {slug}")
        except RuntimeError as e:
            notify(f"Follow-up generation failed: {e}")


def reject_exploration(
    elmer_dir: Path, project_dir: Path, exploration_id: str, *, notify=None,
) -> None:
    """Reject an exploration: delete branch and clean up."""
    if notify is None:
        notify = click.echo

    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)

    if exp is None:
        click.echo(f"Exploration '{exploration_id}' not found.", err=True)
        sys.exit(1)

    if exp["status"] == "approved":
        click.echo("Cannot reject an already-approved exploration.", err=True)
        sys.exit(1)

    _cleanup_worktree(project_dir, exp)

    state.update_exploration(conn, exploration_id, status="rejected")
    conn.close()

    # Execute on_reject chain action
    on_reject = exp["on_reject"] if "on_reject" in exp.keys() else None
    if on_reject:
        _execute_chain_action(
            on_reject, exploration_id, exp["topic"], project_dir, notify=notify,
        )


def approve_all(
    elmer_dir: Path,
    project_dir: Path,
    *,
    auto_followup: bool = False,
    followup_count: int = 3,
    followup_auto_approve: bool = False,
) -> list[str]:
    """Approve all explorations with status 'done'. Returns list of approved IDs."""
    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn, status="done")
    conn.close()

    approved = []
    for exp in explorations:
        try:
            approve_exploration(
                elmer_dir, project_dir, exp["id"],
                auto_followup=auto_followup,
                followup_count=followup_count,
                followup_auto_approve=followup_auto_approve,
            )
            approved.append(exp["id"])
        except SystemExit:
            click.echo(f"Skipping {exp['id']} (merge failed)")
    return approved


def clean_all(elmer_dir: Path, project_dir: Path) -> int:
    """Clean up worktrees for completed explorations. Returns count cleaned."""
    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn)

    cleaned = 0
    for exp in explorations:
        if exp["status"] in ("approved", "rejected"):
            worktree_path = Path(exp["worktree_path"])
            if worktree_path.exists():
                _cleanup_worktree(project_dir, exp)
                cleaned += 1
            state.delete_exploration(conn, exp["id"])
            cleaned += 1

    conn.close()

    # Prune any orphaned worktrees
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=str(project_dir),
        capture_output=True,
    )

    return cleaned
