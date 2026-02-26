"""Shared fixtures for Elmer tests.

Provides isolated .elmer directory and database connection fixtures.
Individual test files can override these when they need custom configuration.
"""

import subprocess

import pytest

from elmer import state


@pytest.fixture
def elmer_dir(tmp_path):
    """Create a minimal .elmer directory with standard subdirectories."""
    d = tmp_path / ".elmer"
    d.mkdir()
    (d / "logs").mkdir()
    return d


@pytest.fixture
def db(elmer_dir):
    """Return a connection to a fresh elmer state database."""
    conn = state.get_db(elmer_dir)
    yield conn
    conn.close()


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo for worktree/branch tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init"], cwd=str(repo), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=str(repo), capture_output=True, check=True,
    )
    return repo
