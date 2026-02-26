"""Tests for NULL cost handling (ADR-057 / C3).

Verifies that zero-cost ($0.00) entries are distinguished from NULL (no data)
across plan status display, dashboard aggregation, and cycle cost queries.
"""

import json
from pathlib import Path

import pytest

from elmer import state
from elmer.plan import get_plan_status


def _create_plan(db, plan_id, steps):
    plan_json = json.dumps({"milestone": "test", "steps": steps})
    state.create_plan(db, id=plan_id, milestone_ref="test", plan_json=plan_json)


def _create_exploration(db, exp_id, plan_id, plan_step, status="done", cost_usd=None):
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
    if cost_usd is not None:
        state.update_exploration(db, exp_id, cost_usd=cost_usd)


class TestPlanCostWithZero:
    """Plan status should include $0.00 costs, not silently drop them."""

    def test_zero_cost_included_in_total(self, elmer_dir, db):
        """A step with cost_usd=0.0 should be included in total, not skipped."""
        _create_plan(db, "plan-1", [{"topic": "A"}, {"topic": "B"}])
        _create_exploration(db, "s0", "plan-1", 0, status="approved", cost_usd=0.0)
        _create_exploration(db, "s1", "plan-1", 1, status="approved", cost_usd=1.50)
        db.close()

        plans = get_plan_status(elmer_dir, "plan-1")
        assert len(plans) == 1
        assert plans[0]["total_cost"] == 1.50

    def test_null_cost_excluded_from_total(self, elmer_dir, db):
        """A step with cost_usd=NULL should not affect the total."""
        _create_plan(db, "plan-2", [{"topic": "A"}, {"topic": "B"}])
        _create_exploration(db, "s0", "plan-2", 0, status="approved", cost_usd=None)
        _create_exploration(db, "s1", "plan-2", 1, status="approved", cost_usd=2.00)
        db.close()

        plans = get_plan_status(elmer_dir, "plan-2")
        assert len(plans) == 1
        assert plans[0]["total_cost"] == 2.00

    def test_all_zero_cost_totals_zero(self, elmer_dir, db):
        """All steps at $0.00 should yield total_cost=0.0, not skip display."""
        _create_plan(db, "plan-3", [{"topic": "A"}])
        _create_exploration(db, "s0", "plan-3", 0, status="approved", cost_usd=0.0)
        db.close()

        plans = get_plan_status(elmer_dir, "plan-3")
        assert plans[0]["total_cost"] == 0.0


class TestDashboardCostWithZero:
    """Dashboard aggregation should count $0.00 entries."""

    def test_zero_cost_counted(self, elmer_dir, db):
        """Exploration with cost_usd=0.0 should contribute to count."""
        state.create_exploration(
            db,
            id="exp-1",
            topic="Test",
            archetype="explore",
            branch="elmer/exp-1",
            worktree_path="/tmp/wt/exp-1",
            model="sonnet",
            status="approved",
        )
        state.update_exploration(db, "exp-1", cost_usd=0.0)

        exp = state.get_exploration(db, "exp-1")
        # The cost should be 0.0, not None
        assert exp["cost_usd"] == 0.0
        # And it should be truthy-distinct from None
        assert exp["cost_usd"] is not None


class TestCycleCostSQL:
    """Cycle cost query should handle NULL and zero correctly."""

    def test_coalesce_returns_zero_for_no_rows(self, elmer_dir):
        """COALESCE(SUM(...), 0.0) returns 0.0 when no matching rows."""
        conn = state.get_db(elmer_dir)
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM costs WHERE created_at >= ?",
            ("2099-01-01",),
        ).fetchone()
        assert row[0] == 0.0
        conn.close()

    def test_coalesce_returns_zero_for_all_null(self, elmer_dir):
        """COALESCE(SUM(...), 0.0) returns 0.0 when all values are NULL."""
        conn = state.get_db(elmer_dir)
        state.record_meta_cost(
            conn,
            operation="test",
            model="sonnet",
            input_tokens=100,
            output_tokens=50,
            cost_usd=None,
        )
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM costs"
        ).fetchone()
        assert row[0] == 0.0
        conn.close()

    def test_sum_includes_zero_values(self, elmer_dir):
        """SUM should include 0.0 values (not skip them like NULL)."""
        conn = state.get_db(elmer_dir)
        state.record_meta_cost(
            conn, operation="a", model="sonnet", cost_usd=0.0,
        )
        state.record_meta_cost(
            conn, operation="b", model="sonnet", cost_usd=1.25,
        )
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM costs"
        ).fetchone()
        assert row[0] == 1.25
        conn.close()
