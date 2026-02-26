"""Tests for A2: plan completion check ordering (ADR-049).

Verifies that is_last_plan_step() correctly identifies the last step,
and that get_completion_verify_cmd() resolves commands with correct priority.
"""

import json
import tempfile
from pathlib import Path

import pytest

from elmer import state
from elmer.implement import get_completion_verify_cmd, is_last_plan_step


@pytest.fixture
def elmer_dir(tmp_path):
    """Create a minimal .elmer directory with a fresh database."""
    d = tmp_path / ".elmer"
    d.mkdir()
    return d


@pytest.fixture
def db(elmer_dir):
    """Return a connection to a fresh elmer state database."""
    conn = state.get_db(elmer_dir)
    yield conn
    conn.close()


def _create_plan(db, elmer_dir, plan_id, steps, completion_verify_cmd=None):
    """Helper: create a plan with optional completion_verify_cmd."""
    plan_data = {"milestone": "test", "steps": steps}
    if completion_verify_cmd:
        plan_data["completion_verify_cmd"] = completion_verify_cmd
    plan_json = json.dumps(plan_data)
    state.create_plan(db, id=plan_id, milestone_ref="test", plan_json=plan_json)


def _create_exploration(db, exp_id, plan_id, plan_step, status="running"):
    """Helper: create a minimal exploration linked to a plan."""
    state.create_exploration(
        db,
        id=exp_id,
        topic=f"Step {plan_step}",
        archetype="implement",
        branch=f"elmer/{exp_id}",
        worktree_path=f"/tmp/wt/{exp_id}",
        model="sonnet",
        plan_id=plan_id,
        plan_step=plan_step,
        status=status,
    )


class TestIsLastPlanStep:
    """Tests for is_last_plan_step()."""

    def test_last_step_when_others_approved(self, elmer_dir, db):
        """Returns True when all other steps are approved."""
        steps = [{"topic": "A"}, {"topic": "B"}, {"topic": "C"}]
        _create_plan(db, elmer_dir, "plan-1", steps)

        _create_exploration(db, "s0", "plan-1", 0, status="approved")
        _create_exploration(db, "s1", "plan-1", 1, status="approved")
        _create_exploration(db, "s2", "plan-1", 2, status="done")

        db.close()
        assert is_last_plan_step(elmer_dir, "plan-1", "s2") is True

    def test_not_last_step_when_others_pending(self, elmer_dir, db):
        """Returns False when other steps are still pending/running."""
        steps = [{"topic": "A"}, {"topic": "B"}, {"topic": "C"}]
        _create_plan(db, elmer_dir, "plan-2", steps)

        _create_exploration(db, "s0", "plan-2", 0, status="approved")
        _create_exploration(db, "s1", "plan-2", 1, status="done")
        _create_exploration(db, "s2", "plan-2", 2, status="pending")

        db.close()
        assert is_last_plan_step(elmer_dir, "plan-2", "s1") is False

    def test_single_step_plan(self, elmer_dir, db):
        """Single-step plan: that step is always the last."""
        steps = [{"topic": "A"}]
        _create_plan(db, elmer_dir, "plan-3", steps)
        _create_exploration(db, "s0", "plan-3", 0, status="done")

        db.close()
        assert is_last_plan_step(elmer_dir, "plan-3", "s0") is True

    def test_nonexistent_plan_returns_false(self, elmer_dir, db):
        """Returns False for nonexistent plan."""
        db.close()
        assert is_last_plan_step(elmer_dir, "nonexistent", "s0") is False


class TestGetCompletionVerifyCmd:
    """Tests for get_completion_verify_cmd()."""

    def test_plan_json_priority(self, elmer_dir, db):
        """completion_verify_cmd from plan JSON takes highest priority."""
        steps = [{"topic": "A", "verify_cmd": "npm test"}]
        _create_plan(db, elmer_dir, "plan-1", steps,
                     completion_verify_cmd="npm run integration-test")

        db.close()
        cmd, source = get_completion_verify_cmd(elmer_dir, "plan-1")
        assert cmd == "npm run integration-test"
        assert "plan" in source

    def test_last_step_fallback(self, elmer_dir, db):
        """Falls back to last step's verify_cmd when no plan-level cmd."""
        steps = [
            {"topic": "A", "verify_cmd": "npm test:unit"},
            {"topic": "B", "verify_cmd": "npm test:e2e"},
        ]
        _create_plan(db, elmer_dir, "plan-2", steps)

        db.close()
        cmd, source = get_completion_verify_cmd(elmer_dir, "plan-2")
        assert cmd == "npm test:e2e"
        assert "last step" in source

    def test_no_cmd_returns_none(self, elmer_dir, db):
        """Returns (None, None) when no verification command exists."""
        steps = [{"topic": "A"}, {"topic": "B"}]
        _create_plan(db, elmer_dir, "plan-3", steps)

        db.close()
        cmd, source = get_completion_verify_cmd(elmer_dir, "plan-3")
        assert cmd is None
        assert source is None

    def test_nonexistent_plan_returns_none(self, elmer_dir, db):
        """Returns (None, None) for nonexistent plan."""
        db.close()
        cmd, source = get_completion_verify_cmd(elmer_dir, "nonexistent")
        assert cmd is None
        assert source is None
