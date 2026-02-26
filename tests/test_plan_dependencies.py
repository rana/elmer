"""Tests for A1: retry dependency management (ADR-049).

Verifies that _rebuild_plan_dependencies() correctly reconstructs the
dependency graph after a plan step is retried, and resets cascade-failed
dependents to pending.
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from elmer import state
from elmer.gate import _rebuild_plan_dependencies


def _create_plan(db, elmer_dir, plan_id, steps):
    """Helper: create a plan with the given steps JSON."""
    plan_json = json.dumps({"milestone": "test", "steps": steps})
    state.create_plan(db, id=plan_id, milestone_ref="test", plan_json=plan_json)


def _create_exploration(db, exp_id, plan_id, plan_step, status="running", summary=None):
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
    if summary:
        state.update_exploration(db, exp_id, proposal_summary=summary)


class TestRebuildPlanDependencies:
    """Tests for _rebuild_plan_dependencies()."""

    def test_basic_rebuild(self, elmer_dir, db):
        """Rebuilding deps after retry creates correct dependency records."""
        # Plan: step 0 -> step 1 -> step 2
        steps = [
            {"topic": "A", "depends_on": []},
            {"topic": "B", "depends_on": [0]},
            {"topic": "C", "depends_on": [1]},
        ]
        _create_plan(db, elmer_dir, "plan-1", steps)

        # Simulate: step-0 retried as step-0-2, step-1 and step-2 exist
        _create_exploration(db, "step-0-2", "plan-1", 0, status="approved")
        _create_exploration(db, "step-1", "plan-1", 1, status="failed",
                            summary="(dependency failed: step-0)")
        _create_exploration(db, "step-2", "plan-1", 2, status="failed",
                            summary="(dependency failed: step-1)")

        # Before rebuild: no dependency records exist (step-0 was deleted)
        assert state.get_dependencies(db, "step-1") == []
        assert state.get_dependencies(db, "step-2") == []

        db.close()  # _rebuild_plan_dependencies opens its own connection
        reset = _rebuild_plan_dependencies(elmer_dir, "plan-1")

        # Verify: dependencies rebuilt
        db2 = state.get_db(elmer_dir)
        assert state.get_dependencies(db2, "step-1") == ["step-0-2"]
        assert state.get_dependencies(db2, "step-2") == ["step-1"]

        # Verify: cascade-failed steps reset to pending
        exp1 = state.get_exploration(db2, "step-1")
        exp2 = state.get_exploration(db2, "step-2")
        assert exp1["status"] == "pending"
        assert exp2["status"] == "pending"
        assert exp1["proposal_summary"] is None
        assert exp2["proposal_summary"] is None

        # Return value
        assert reset == 2

        db2.close()

    def test_no_cascade_failures_doesnt_reset(self, elmer_dir, db):
        """Non-cascade failures are not reset to pending."""
        steps = [
            {"topic": "A", "depends_on": []},
            {"topic": "B", "depends_on": [0]},
        ]
        _create_plan(db, elmer_dir, "plan-2", steps)

        _create_exploration(db, "step-0", "plan-2", 0, status="approved")
        _create_exploration(db, "step-1", "plan-2", 1, status="failed",
                            summary="verification failed: npm test")

        db.close()
        reset = _rebuild_plan_dependencies(elmer_dir, "plan-2")

        # step-1 has a real failure, not cascade — should NOT be reset
        db2 = state.get_db(elmer_dir)
        exp1 = state.get_exploration(db2, "step-1")
        assert exp1["status"] == "failed"
        assert reset == 0
        db2.close()

    def test_replaces_stale_deps(self, elmer_dir, db):
        """Existing dependency records are replaced, not duplicated."""
        steps = [
            {"topic": "A", "depends_on": []},
            {"topic": "B", "depends_on": [0]},
        ]
        _create_plan(db, elmer_dir, "plan-3", steps)

        _create_exploration(db, "step-0-2", "plan-3", 0, status="running")
        _create_exploration(db, "step-1", "plan-3", 1, status="pending")

        # Add a stale dependency (from before retry)
        state.add_dependency(db, "step-1", "step-0-old")

        db.close()
        _rebuild_plan_dependencies(elmer_dir, "plan-3")

        # Stale dep replaced with correct one
        db2 = state.get_db(elmer_dir)
        deps = state.get_dependencies(db2, "step-1")
        assert deps == ["step-0-2"]
        assert "step-0-old" not in deps
        db2.close()

    def test_missing_plan_returns_zero(self, elmer_dir, db):
        """Returns 0 for nonexistent plan without error."""
        db.close()
        reset = _rebuild_plan_dependencies(elmer_dir, "nonexistent")
        assert reset == 0

    def test_parallel_deps_rebuilt(self, elmer_dir, db):
        """Steps with multiple dependencies are rebuilt correctly."""
        # Plan: step 0, step 1 (parallel), step 2 depends on both
        steps = [
            {"topic": "A", "depends_on": []},
            {"topic": "B", "depends_on": []},
            {"topic": "C", "depends_on": [0, 1]},
        ]
        _create_plan(db, elmer_dir, "plan-4", steps)

        _create_exploration(db, "s0", "plan-4", 0, status="approved")
        _create_exploration(db, "s1", "plan-4", 1, status="approved")
        _create_exploration(db, "s2", "plan-4", 2, status="failed",
                            summary="(dependency failed: s0-old)")

        db.close()
        _rebuild_plan_dependencies(elmer_dir, "plan-4")

        db2 = state.get_db(elmer_dir)
        deps = sorted(state.get_dependencies(db2, "s2"))
        assert deps == ["s0", "s1"]
        db2.close()
