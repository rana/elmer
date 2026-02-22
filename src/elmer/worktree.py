"""Git worktree operations."""

import subprocess
from pathlib import Path


def create_worktree(project_dir: Path, branch_name: str, worktree_path: Path) -> None:
    """Create a git worktree on a new branch."""
    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", branch_name],
        cwd=str(project_dir),
        check=True,
        capture_output=True,
        text=True,
    )


def remove_worktree(project_dir: Path, worktree_path: Path) -> None:
    """Remove a git worktree."""
    subprocess.run(
        ["git", "worktree", "remove", str(worktree_path), "--force"],
        cwd=str(project_dir),
        check=True,
        capture_output=True,
        text=True,
    )


def delete_branch(project_dir: Path, branch_name: str) -> None:
    """Delete a git branch."""
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        cwd=str(project_dir),
        check=True,
        capture_output=True,
        text=True,
    )


def merge_branch(project_dir: Path, branch_name: str, message: str) -> None:
    """Merge a branch into the current branch."""
    subprocess.run(
        ["git", "merge", branch_name, "--no-ff", "-m", message],
        cwd=str(project_dir),
        check=True,
        capture_output=True,
        text=True,
    )


def branch_exists(project_dir: Path, branch_name: str) -> bool:
    """Check if a git branch exists."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def get_branch_diff(project_dir: Path, branch_name: str) -> str:
    """Get a diff stat of changes on a branch relative to its merge base."""
    result = subprocess.run(
        ["git", "diff", f"HEAD...{branch_name}", "--stat"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "(diff unavailable)"


def get_project_root() -> Path:
    """Find the git root of the current directory."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Not in a git repository")
    return Path(result.stdout.strip())
