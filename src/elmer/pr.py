"""PR-based review — push branch and create GitHub PR from exploration."""

import subprocess
import sys
from pathlib import Path

import click

from . import state


def _check_gh_available() -> bool:
    """Check if gh CLI is installed."""
    try:
        subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
        )
        return True
    except FileNotFoundError:
        return False


def push_branch(project_dir: Path, branch: str) -> None:
    """Push an exploration branch to the remote."""
    result = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git push failed:\n{result.stderr.strip()}")


def create_pr(
    project_dir: Path,
    branch: str,
    title: str,
    body: str,
) -> str:
    """Create a GitHub PR using gh CLI. Returns the PR URL."""
    result = subprocess.run(
        [
            "gh", "pr", "create",
            "--head", branch,
            "--title", title,
            "--body", body,
        ],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh pr create failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def create_pr_for_exploration(
    elmer_dir: Path,
    project_dir: Path,
    exploration_id: str,
) -> str:
    """Push branch and create PR for an exploration. Returns PR URL."""
    if not _check_gh_available():
        raise RuntimeError(
            "gh CLI not found. Install it: https://cli.github.com/"
        )

    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)
    conn.close()

    if exp is None:
        click.echo(f"Exploration '{exploration_id}' not found.", err=True)
        sys.exit(1)

    if exp["status"] not in ("done", "failed", "running"):
        click.echo(
            f"Cannot create PR for exploration in status '{exp['status']}'.",
            err=True,
        )
        sys.exit(1)

    branch = exp["branch"]
    topic = exp["topic"]
    title = f"elmer: {topic}"
    if len(title) > 70:
        title = title[:67] + "..."

    # Build PR body from PROPOSAL.md
    worktree_path = Path(exp["worktree_path"])
    proposal_path = worktree_path / "PROPOSAL.md"

    if proposal_path.exists():
        body = proposal_path.read_text()
    else:
        body = f"Elmer exploration: {topic}\n\nNo PROPOSAL.md generated."

    body += f"\n\n---\n*Created by [Elmer](https://github.com) — exploration `{exploration_id}`*"

    # Push the branch
    click.echo(f"Pushing branch {branch}...")
    push_branch(project_dir, branch)

    # Create the PR
    click.echo("Creating PR...")
    pr_url = create_pr(project_dir, branch, title, body)

    return pr_url
