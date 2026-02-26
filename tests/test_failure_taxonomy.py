"""Failure taxonomy tests — structured failure categories (ADR-076).

Verifies that failure_category is stored in the DB, populated correctly
by _diagnose_failure, and exposed through the schema.
"""

import json

import pytest

from elmer import state
from elmer.review import (
    _diagnose_failure,
    FAILURE_NO_LOG,
    FAILURE_EMPTY_LOG,
    FAILURE_LOG_CORRUPT,
    FAILURE_CLAUDE_ERROR,
    FAILURE_WRONG_PATH,
    FAILURE_PROPOSAL_MISSING,
    FAILURE_PERMISSION_DENIED,
    FAILURE_NO_PROPOSAL,
)


class TestFailureCategorySchema:
    """Verify failure_category column exists and round-trips."""

    def test_column_exists(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(explorations)").fetchall()}
        assert "failure_category" in cols

    def test_default_is_null(self, db):
        state.create_exploration(
            db, id="fc-null", topic="Test", archetype="explore",
            branch="elmer/fc-null", worktree_path="/tmp/wt/fc-null",
            model="sonnet",
        )
        exp = state.get_exploration(db, "fc-null")
        assert exp["failure_category"] is None

    def test_stores_and_retrieves(self, db):
        state.create_exploration(
            db, id="fc-store", topic="Test", archetype="explore",
            branch="elmer/fc-store", worktree_path="/tmp/wt/fc-store",
            model="sonnet",
        )
        state.update_exploration(db, "fc-store",
                                 status="failed",
                                 failure_category="verification_exhausted")
        exp = state.get_exploration(db, "fc-store")
        assert exp["failure_category"] == "verification_exhausted"


class TestDiagnoseFailure:
    """Verify _diagnose_failure returns (category, reason) tuples."""

    def test_no_log_file(self, tmp_path):
        cat, reason = _diagnose_failure(tmp_path / "nonexistent.log")
        assert cat == FAILURE_NO_LOG
        assert "no log file" in reason

    def test_empty_log_file(self, tmp_path):
        log = tmp_path / "empty.log"
        log.write_text("")
        cat, reason = _diagnose_failure(log)
        assert cat == FAILURE_EMPTY_LOG
        assert "empty log" in reason

    def test_corrupt_log(self, tmp_path):
        log = tmp_path / "bad.log"
        log.write_text("not json at all{{{")
        cat, reason = _diagnose_failure(log)
        assert cat == FAILURE_LOG_CORRUPT
        assert "not valid JSON" in reason

    def test_claude_error(self, tmp_path):
        log = tmp_path / "error.log"
        log.write_text(json.dumps({
            "type": "result",
            "is_error": True,
            "result": "API rate limit exceeded",
        }))
        cat, reason = _diagnose_failure(log)
        assert cat == FAILURE_CLAUDE_ERROR
        assert "API rate limit" in reason

    def test_wrong_path(self, tmp_path):
        log = tmp_path / "wrong.log"
        log.write_text(json.dumps({
            "type": "result",
            "is_error": False,
            "result": "I have written PROPOSAL.md to /wrong/path/PROPOSAL.md",
        }))
        cat, reason = _diagnose_failure(log)
        assert cat == FAILURE_WRONG_PATH
        assert "wrong path" in reason

    def test_proposal_mentioned_but_missing(self, tmp_path):
        log = tmp_path / "missing.log"
        log.write_text(json.dumps({
            "type": "result",
            "is_error": False,
            "result": "I created the proposal document.",
        }))
        cat, reason = _diagnose_failure(log)
        assert cat == FAILURE_PROPOSAL_MISSING
        assert "not found" in reason

    def test_permission_denied(self, tmp_path):
        log = tmp_path / "perm.log"
        log.write_text(json.dumps({
            "type": "result",
            "is_error": False,
            "result": "I tried but couldn't write.",
            "permission_denials": [
                {"tool_name": "Write", "tool_input": {"path": "/etc/shadow"}},
            ],
        }))
        cat, reason = _diagnose_failure(log)
        assert cat == FAILURE_PERMISSION_DENIED
        assert "permission denial" in reason

    def test_normal_completion_no_proposal(self, tmp_path):
        log = tmp_path / "normal.log"
        log.write_text(json.dumps({
            "type": "result",
            "is_error": False,
            "result": "All done!",
            "num_turns": 15,
        }))
        cat, reason = _diagnose_failure(log)
        assert cat == FAILURE_NO_PROPOSAL
        assert "15 turns" in reason

    def test_streaming_format(self, tmp_path):
        """Handles streaming log format (list of objects)."""
        log = tmp_path / "stream.log"
        log.write_text(json.dumps([
            {"type": "progress", "content": "working..."},
            {"type": "result", "is_error": True, "result": "out of context"},
        ]))
        cat, reason = _diagnose_failure(log)
        assert cat == FAILURE_CLAUDE_ERROR
        assert "out of context" in reason
