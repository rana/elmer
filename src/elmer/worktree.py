"""Git worktree operations."""

import subprocess
from pathlib import Path
from typing import Optional


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


def merge_branch(
    project_dir: Path, branch_name: str, message: str, *,
    strategy_option: str | None = None,
) -> None:
    """Merge a branch into the current branch.

    strategy_option: passed as -X (e.g., 'theirs') for conflict resolution.
    """
    cmd = ["git", "merge", branch_name, "--no-ff", "-m", message]
    if strategy_option:
        cmd.extend(["-X", strategy_option])
    subprocess.run(
        cmd,
        cwd=str(project_dir),
        check=True,
        capture_output=True,
        text=True,
    )


def abort_merge(project_dir: Path) -> None:
    """Abort an in-progress merge. Best-effort — ignores errors if no merge is active."""
    subprocess.run(
        ["git", "merge", "--abort"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )


def remove_file_and_commit(project_dir: Path, filename: str, message: str) -> None:
    """Remove a file from the working tree and commit the deletion."""
    filepath = project_dir / filename
    if not filepath.exists():
        return
    subprocess.run(
        ["git", "rm", "-f", filename],
        cwd=str(project_dir),
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(project_dir),
        check=True,
        capture_output=True,
        text=True,
    )


def is_ancestor(project_dir: Path, branch_name: str) -> bool:
    """Check if a branch is already merged (ancestor of HEAD).

    Returns True if the branch tip is reachable from HEAD, meaning
    its changes are already incorporated. Used to skip redundant merges
    during crash recovery.
    """
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", branch_name, "HEAD"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


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


def read_file_from_branch(project_dir: Path, branch_name: str, file_path: str) -> Optional[str]:
    """Read a file's content from a branch without checking out.

    Returns the file content as string, or None if the branch or file doesn't exist.
    Used for crash recovery when a worktree is gone but the branch survives.
    """
    result = subprocess.run(
        ["git", "show", f"{branch_name}:{file_path}"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def commit_proposal_to_branch(worktree_path: Path, exploration_id: str) -> bool:
    """Commit PROPOSAL.md to the exploration branch inside its worktree.

    Called when an exploration transitions to 'done'. Ensures the proposal
    is tracked by git and recoverable via 'git show <branch>:PROPOSAL.md'
    even after the worktree is removed (ADR-034).

    Returns True if a commit was created, False if skipped (already tracked,
    no proposal, or error).
    """
    proposal = worktree_path / "PROPOSAL.md"
    if not proposal.exists():
        return False

    # Check if PROPOSAL.md is already tracked and unchanged
    status = subprocess.run(
        ["git", "status", "--porcelain", "PROPOSAL.md"],
        cwd=str(worktree_path),
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        return False
    # If status output is empty, file is tracked and unchanged — skip
    if not status.stdout.strip():
        return False

    try:
        subprocess.run(
            ["git", "add", "PROPOSAL.md"],
            cwd=str(worktree_path),
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Save PROPOSAL.md for {exploration_id}"],
            cwd=str(worktree_path),
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


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
