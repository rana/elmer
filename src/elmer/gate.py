"""Approval gate — approve (merge) or reject (discard) explorations."""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from . import state, worktree


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


def approve_exploration(
    elmer_dir: Path, project_dir: Path, exploration_id: str
) -> None:
    """Approve an exploration: merge its branch and clean up."""
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

    # Cleanup
    _cleanup_worktree(project_dir, exp)

    state.update_exploration(
        conn,
        exploration_id,
        status="approved",
        merged_at=datetime.now(timezone.utc).isoformat(),
    )
    conn.close()


def reject_exploration(
    elmer_dir: Path, project_dir: Path, exploration_id: str
) -> None:
    """Reject an exploration: delete branch and clean up."""
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


def approve_all(elmer_dir: Path, project_dir: Path) -> list[str]:
    """Approve all explorations with status 'done'. Returns list of approved IDs."""
    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn, status="done")
    conn.close()

    approved = []
    for exp in explorations:
        try:
            approve_exploration(elmer_dir, project_dir, exp["id"])
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
