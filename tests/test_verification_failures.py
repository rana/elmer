"""Tests for verification failure tracking (ADR-059 / C1).

Verifies that the verification_failures counter increments correctly
and is surfaced in plan status.
"""

import json
from pathlib import Path

import pytest

from elmer import state
from elmer.plan import get_plan_status


@pytest.fixture
def elmer_dir(tmp_path):
    d = tmp_path / ".elmer"
    d.mkdir()
    return d


@pytest.fixture
def db(elmer_dir):
    conn = state.get_db(elmer_dir)
    yield conn
    conn.close()


class TestIncrementVerificationFailures:
    """Tests for state.increment_verification_failures()."""

    def test_first_increment(self, db):
        """First increment returns 1."""
        state.create_exploration(
            db,
            id="exp-1",
            topic="Test",
            archetype="explore",
            branch="elmer/exp-1",
            worktree_path="/tmp/wt/exp-1",
            model="sonnet",
            status="running",
        )
        count = state.increment_verification_failures(db, "exp-1")
        assert count == 1

    def test_multiple_increments(self, db):
        """Successive increments accumulate correctly."""
        state.create_exploration(
            db,
            id="exp-2",
            topic="Test",
            archetype="explore",
            branch="elmer/exp-2",
            worktree_path="/tmp/wt/exp-2",
            model="sonnet",
            status="running",
        )
        state.increment_verification_failures(db, "exp-2")
        state.increment_verification_failures(db, "exp-2")
        count = state.increment_verification_failures(db, "exp-2")
        assert count == 3

    def test_default_is_zero(self, db):
        """New explorations start with verification_failures=0."""
        state.create_exploration(
            db,
            id="exp-3",
            topic="Test",
            archetype="explore",
            branch="elmer/exp-3",
            worktree_path="/tmp/wt/exp-3",
            model="sonnet",
            status="running",
        )
        exp = state.get_exploration(db, "exp-3")
        assert exp["verification_failures"] == 0

    def test_nonexistent_returns_zero(self, db):
        """Incrementing a nonexistent exploration returns 0."""
        count = state.increment_verification_failures(db, "nonexistent")
        assert count == 0


class TestPlanStatusVerificationFailures:
    """Tests for verification_failures in plan status display."""

    def test_vfails_in_step_info(self, elmer_dir, db):
        """Verification failures are included in step status data."""
        plan_json = json.dumps({"milestone": "test", "steps": [{"topic": "A"}]})
        state.create_plan(db, id="plan-1", milestone_ref="test", plan_json=plan_json)
        state.create_exploration(
            db,
            id="s0",
            topic="Step 0",
            archetype="implement",
            branch="elmer/s0",
            worktree_path="/tmp/wt/s0",
            model="sonnet",
            plan_id="plan-1",
            plan_step=0,
            status="done",
        )
        # Simulate 2 verification failures
        state.increment_verification_failures(db, "s0")
        state.increment_verification_failures(db, "s0")
        db.close()

        plans = get_plan_status(elmer_dir, "plan-1")
        assert len(plans) == 1
        assert plans[0]["steps"][0]["verification_failures"] == 2


class TestVerificationSeconds:
    """Tests for verification_seconds accumulation (ADR-060)."""

    def test_default_is_zero(self, db):
        """New explorations start with verification_seconds=0."""
        state.create_exploration(
            db,
            id="exp-vs",
            topic="Test",
            archetype="explore",
            branch="elmer/exp-vs",
            worktree_path="/tmp/wt/exp-vs",
            model="sonnet",
            status="running",
        )
        exp = state.get_exploration(db, "exp-vs")
        assert exp["verification_seconds"] == 0

    def test_accumulation_via_sql(self, db):
        """Direct SQL accumulation works correctly."""
        state.create_exploration(
            db,
            id="exp-acc",
            topic="Test",
            archetype="explore",
            branch="elmer/exp-acc",
            worktree_path="/tmp/wt/exp-acc",
            model="sonnet",
            status="running",
        )
        # Simulate accumulation
        db.execute(
            "UPDATE explorations SET verification_seconds = COALESCE(verification_seconds, 0) + ? WHERE id = ?",
            (1.5, "exp-acc"),
        )
        db.commit()
        db.execute(
            "UPDATE explorations SET verification_seconds = COALESCE(verification_seconds, 0) + ? WHERE id = ?",
            (2.3, "exp-acc"),
        )
        db.commit()
        exp = state.get_exploration(db, "exp-acc")
        assert abs(exp["verification_seconds"] - 3.8) < 0.01

    def test_vseconds_in_plan_status(self, elmer_dir, db):
        """Verification seconds are included in plan step status."""
        plan_json = json.dumps({"milestone": "test", "steps": [{"topic": "A"}]})
        state.create_plan(db, id="plan-vs", milestone_ref="test", plan_json=plan_json)
        state.create_exploration(
            db,
            id="s0-vs",
            topic="Step 0",
            archetype="implement",
            branch="elmer/s0-vs",
            worktree_path="/tmp/wt/s0-vs",
            model="sonnet",
            plan_id="plan-vs",
            plan_step=0,
            status="done",
        )
        db.execute(
            "UPDATE explorations SET verification_seconds = 12.5 WHERE id = ?",
            ("s0-vs",),
        )
        db.commit()
        db.close()

        plans = get_plan_status(elmer_dir, "plan-vs")
        assert plans[0]["steps"][0]["verification_seconds"] == 12.5
