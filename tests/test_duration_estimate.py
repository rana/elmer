"""Tests for plan step duration estimation (ADR-061 / F2).

Verifies that estimate_plan_duration() correctly sums estimated_seconds
from plan steps and produces appropriate warnings.
"""

import pytest

from elmer.decompose import estimate_plan_duration


class TestEstimatePlanDuration:
    """Tests for estimate_plan_duration()."""

    def test_no_estimates_returns_none(self):
        """Returns None when no steps have estimated_seconds."""
        plan = {"steps": [{"topic": "A"}, {"topic": "B"}]}
        total, warnings = estimate_plan_duration(plan)
        assert total is None
        assert warnings == []

    def test_all_steps_estimated(self):
        """Sums all estimated_seconds when all steps provide them."""
        plan = {"steps": [
            {"topic": "A", "estimated_seconds": 600},
            {"topic": "B", "estimated_seconds": 1200},
        ]}
        total, warnings = estimate_plan_duration(plan)
        assert total == 1800
        assert warnings == []

    def test_partial_estimates_warns(self):
        """Warns when some steps lack estimates."""
        plan = {"steps": [
            {"topic": "A", "estimated_seconds": 600},
            {"topic": "B"},
        ]}
        total, warnings = estimate_plan_duration(plan)
        assert total == 600
        assert any("1/2 steps have no duration estimate" in w for w in warnings)

    def test_invalid_estimate_warns(self):
        """Warns on non-numeric estimated_seconds."""
        plan = {"steps": [
            {"topic": "A", "estimated_seconds": "fast"},
        ]}
        total, warnings = estimate_plan_duration(plan)
        assert total is None
        assert any("invalid estimated_seconds" in w for w in warnings)

    def test_negative_estimate_warns(self):
        """Warns on negative estimated_seconds."""
        plan = {"steps": [
            {"topic": "A", "estimated_seconds": -100},
        ]}
        total, warnings = estimate_plan_duration(plan)
        assert total is None
        assert any("invalid estimated_seconds" in w for w in warnings)

    def test_empty_plan(self):
        """Empty plan returns None with no warnings."""
        plan = {"steps": []}
        total, warnings = estimate_plan_duration(plan)
        assert total is None
        assert warnings == []

    def test_zero_seconds_valid(self):
        """Zero is a valid estimate (instant operation)."""
        plan = {"steps": [
            {"topic": "A", "estimated_seconds": 0},
            {"topic": "B", "estimated_seconds": 300},
        ]}
        total, warnings = estimate_plan_duration(plan)
        assert total == 300
        assert warnings == []
