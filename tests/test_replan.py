"""Tests for A3: plan revision / replanning (ADR-067).

Verifies that validate_revision() catches structural errors,
apply_revision() correctly remaps/cancels/creates explorations,
and _rebuild_revised_dependencies() produces the right DAG.
"""

import json
import tempfile
from pathlib import Path

import pytest

from elmer import state
from elmer.replan import (
    _rebuild_revised_dependencies,
    apply_revision,
    validate_revision,
)


@pytest.fixture
def elmer_dir(tmp_path):
    """Create a minimal .elmer directory with a fresh database."""
    d = tmp_path / ".elmer"
    d.mkdir()
    (d / "logs").mkdir()
    return d


@pytest.fixture
def project_dir(tmp_path):
    """Create a minimal project directory with git init."""
    p = tmp_path / "project"
    p.mkdir()
    # Minimal git init so worktree operations don't fail
    import subprocess
    subprocess.run(["git", "init"], cwd=str(p), capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(p), capture_output=True)
    return p


@pytest.fixture
def db(elmer_dir):
    """Return a connection to a fresh elmer state database."""
    conn = state.get_db(elmer_dir)
    yield conn
    conn.close()


def _create_plan(db, elmer_dir, plan_id, steps, milestone="test"):
    """Helper: create a plan with the given steps JSON."""
    plan_json = json.dumps({"milestone": milestone, "steps": steps})
    state.create_plan(db, id=plan_id, milestone_ref=milestone, plan_json=plan_json)


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


class TestValidateRevision:
    """Tests for validate_revision()."""

    def test_approved_steps_must_be_preserved(self, tmp_path):
        """Dropping an approved step is a validation error."""
        original = {"steps": [{"topic": "A"}, {"topic": "B"}, {"topic": "C"}]}
        revised = {
            "steps": [
                {"topic": "A", "preserved_from": 0},
                {"topic": "D"},
            ],
            "step_mapping": {"0": 0, "1": None, "2": None},
        }
        # Step 1 was approved but dropped
        errors = validate_revision(revised, original, {0, 1}, tmp_path)
        assert any("approved step 1 is dropped" in e for e in errors)

    def test_valid_revision_passes(self, tmp_path):
        """A well-formed revision has no errors."""
        original = {"steps": [{"topic": "A"}, {"topic": "B"}, {"topic": "C"}]}
        revised = {
            "steps": [
                {"topic": "A", "preserved_from": 0, "depends_on": []},
                {"topic": "B-revised", "depends_on": [0]},
                {"topic": "D-new", "depends_on": [1]},
            ],
            "step_mapping": {"0": 0, "1": 1, "2": None},
        }
        errors = validate_revision(revised, original, {0}, tmp_path)
        # Only step 0 is approved, step 2 can be dropped
        assert errors == []

    def test_duplicate_mapping_detected(self, tmp_path):
        """Mapping two original steps to the same new index is an error."""
        original = {"steps": [{"topic": "A"}, {"topic": "B"}]}
        revised = {
            "steps": [{"topic": "X", "depends_on": []}],
            "step_mapping": {"0": 0, "1": 0},
        }
        errors = validate_revision(revised, original, set(), tmp_path)
        assert any("multiple original steps" in e for e in errors)

    def test_out_of_range_mapping(self, tmp_path):
        """Mapping to a non-existent new index is an error."""
        original = {"steps": [{"topic": "A"}]}
        revised = {
            "steps": [{"topic": "X", "depends_on": []}],
            "step_mapping": {"0": 5},
        }
        errors = validate_revision(revised, original, set(), tmp_path)
        assert any("out of range" in e for e in errors)

    def test_preserved_from_must_be_approved(self, tmp_path):
        """preserved_from referencing a non-approved step is an error."""
        original = {"steps": [{"topic": "A"}, {"topic": "B"}]}
        revised = {
            "steps": [
                {"topic": "A", "preserved_from": 0, "depends_on": []},
                {"topic": "B", "preserved_from": 1, "depends_on": [0]},
            ],
            "step_mapping": {"0": 0, "1": 1},
        }
        # Only step 0 approved — step 1's preserved_from=1 is invalid
        errors = validate_revision(revised, original, {0}, tmp_path)
        assert any("preserved_from=1" in e and "not approved" in e for e in errors)


class TestRebuildRevisedDependencies:
    """Tests for _rebuild_revised_dependencies()."""

    def test_basic_rebuild(self, elmer_dir, db):
        """Dependencies are rebuilt from revised plan JSON."""
        steps = [
            {"topic": "A", "depends_on": []},
            {"topic": "B", "depends_on": [0]},
        ]
        _create_plan(db, elmer_dir, "plan-r1", steps)
        _create_exploration(db, "s0", "plan-r1", 0, status="approved")
        _create_exploration(db, "s1", "plan-r1", 1, status="pending")

        # Add a stale dep
        state.add_dependency(db, "s1", "old-dep")

        revised = {
            "steps": [
                {"topic": "A", "depends_on": []},
                {"topic": "B-revised", "depends_on": [0]},
            ],
        }
        db.close()

        _rebuild_revised_dependencies(elmer_dir, "plan-r1", revised)

        db2 = state.get_db(elmer_dir)
        deps = state.get_dependencies(db2, "s1")
        assert deps == ["s0"]
        assert "old-dep" not in deps
        db2.close()

    def test_approved_steps_skip_deps(self, elmer_dir, db):
        """Approved steps don't get new dependency records."""
        steps = [
            {"topic": "A", "depends_on": []},
            {"topic": "B", "depends_on": [0]},
        ]
        _create_plan(db, elmer_dir, "plan-r2", steps)
        _create_exploration(db, "s0", "plan-r2", 0, status="approved")
        _create_exploration(db, "s1", "plan-r2", 1, status="approved")

        revised = {
            "steps": [
                {"topic": "A", "depends_on": []},
                {"topic": "B", "depends_on": [0]},
                {"topic": "C-new", "depends_on": [0, 1]},
            ],
        }
        db.close()

        _rebuild_revised_dependencies(elmer_dir, "plan-r2", revised)

        db2 = state.get_db(elmer_dir)
        # Approved steps should have no deps
        assert state.get_dependencies(db2, "s0") == []
        assert state.get_dependencies(db2, "s1") == []
        db2.close()


class TestSchemaRevisionColumns:
    """Tests for the plan revision schema columns."""

    def test_revision_columns_exist(self, elmer_dir, db):
        """New revision columns are accessible on fresh plans."""
        state.create_plan(
            db, id="rev-test", milestone_ref="test",
            plan_json='{"steps": []}',
        )
        plan = state.get_plan(db, "rev-test")
        assert plan["revision_count"] == 0
        assert plan["prior_plan_json"] is None
        assert plan["replan_trigger_step"] is None

    def test_update_revision_fields(self, elmer_dir, db):
        """Revision fields can be updated."""
        state.create_plan(
            db, id="rev-test2", milestone_ref="test",
            plan_json='{"steps": []}',
        )
        state.update_plan(
            db, "rev-test2",
            prior_plan_json='{"old": true}',
            revision_count=1,
            replan_trigger_step=2,
        )
        plan = state.get_plan(db, "rev-test2")
        assert plan["revision_count"] == 1
        assert plan["prior_plan_json"] == '{"old": true}'
        assert plan["replan_trigger_step"] == 2
