"""Worktree boundary tests — git operations against real temp repos (ADR-075).

Guards the dangerous layer: worktree operations modify the user's git repo.
A bug here can corrupt branches or leave orphaned worktrees.
"""

import subprocess

import pytest

from elmer.worktree import (
    branch_exists,
    create_worktree,
    delete_branch,
    is_ancestor,
    merge_branch,
    read_file_from_branch,
    remove_worktree,
)


class TestCreateAndRemoveWorktree:
    """Verify worktree lifecycle: create, verify, remove, verify gone."""

    def test_create_worktree(self, git_repo, tmp_path):
        wt_path = tmp_path / "wt"
        create_worktree(git_repo, "test-branch", wt_path)
        assert wt_path.exists()
        assert (wt_path / ".git").exists()
        assert branch_exists(git_repo, "test-branch")

    def test_remove_worktree(self, git_repo, tmp_path):
        wt_path = tmp_path / "wt"
        create_worktree(git_repo, "rm-branch", wt_path)
        remove_worktree(git_repo, wt_path)
        assert not wt_path.exists()

    def test_create_duplicate_branch_fails(self, git_repo, tmp_path):
        """Creating a worktree with an existing branch name fails."""
        wt1 = tmp_path / "wt1"
        wt2 = tmp_path / "wt2"
        create_worktree(git_repo, "dup-branch", wt1)
        with pytest.raises(subprocess.CalledProcessError):
            create_worktree(git_repo, "dup-branch", wt2)


class TestBranchOperations:
    """Verify branch existence, deletion, and ancestry checks."""

    def test_branch_exists_true(self, git_repo, tmp_path):
        wt = tmp_path / "wt"
        create_worktree(git_repo, "exists-branch", wt)
        assert branch_exists(git_repo, "exists-branch") is True

    def test_branch_exists_false(self, git_repo):
        assert branch_exists(git_repo, "no-such-branch") is False

    def test_delete_branch(self, git_repo, tmp_path):
        wt = tmp_path / "wt"
        create_worktree(git_repo, "del-branch", wt)
        remove_worktree(git_repo, wt)
        delete_branch(git_repo, "del-branch")
        assert branch_exists(git_repo, "del-branch") is False

    def test_is_ancestor_after_merge(self, git_repo, tmp_path):
        """After merging a branch, it should be an ancestor of HEAD."""
        wt = tmp_path / "wt"
        create_worktree(git_repo, "anc-branch", wt)

        # Create a commit on the branch
        (wt / "file.txt").write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=str(wt), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add file"],
            cwd=str(wt), check=True, capture_output=True,
        )

        remove_worktree(git_repo, wt)
        merge_branch(git_repo, "anc-branch", "Merge anc-branch")
        assert is_ancestor(git_repo, "anc-branch") is True

    def test_is_ancestor_unmerged(self, git_repo, tmp_path):
        """An unmerged branch with commits is not an ancestor of HEAD."""
        wt = tmp_path / "wt"
        create_worktree(git_repo, "unmerged-branch", wt)

        (wt / "file.txt").write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=str(wt), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add file"],
            cwd=str(wt), check=True, capture_output=True,
        )

        remove_worktree(git_repo, wt)
        assert is_ancestor(git_repo, "unmerged-branch") is False


class TestReadFileFromBranch:
    """Verify reading files from branches without checkout."""

    def test_read_existing_file(self, git_repo, tmp_path):
        wt = tmp_path / "wt"
        create_worktree(git_repo, "read-branch", wt)

        (wt / "PROPOSAL.md").write_text("# Test Proposal")
        subprocess.run(["git", "add", "PROPOSAL.md"], cwd=str(wt), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add proposal"],
            cwd=str(wt), check=True, capture_output=True,
        )
        remove_worktree(git_repo, wt)

        content = read_file_from_branch(git_repo, "read-branch", "PROPOSAL.md")
        assert content is not None
        assert "# Test Proposal" in content

    def test_read_nonexistent_file(self, git_repo, tmp_path):
        wt = tmp_path / "wt"
        create_worktree(git_repo, "read-none", wt)
        remove_worktree(git_repo, wt)
        content = read_file_from_branch(git_repo, "read-none", "NOPE.md")
        assert content is None

    def test_read_nonexistent_branch(self, git_repo):
        content = read_file_from_branch(git_repo, "no-branch", "file.txt")
        assert content is None
