"""State contract tests — schema, CRUD, defaults, query contracts (ADR-075).

Guards the foundation layer: every module reads/writes through state.py.
A schema drift or CRUD bug silently corrupts everything downstream.
"""

import json

import pytest

from elmer import state


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestSchema:
    """Verify that get_db() creates all expected tables with correct structure."""

    def test_explorations_table_exists(self, db):
        """The explorations table is created with expected columns."""
        cols = {row[1] for row in db.execute("PRAGMA table_info(explorations)").fetchall()}
        expected = {
            "id", "topic", "archetype", "branch", "worktree_path", "status",
            "model", "pid", "created_at", "completed_at", "merged_at",
            "proposal_summary", "parent_id", "max_turns", "auto_approve",
            "generate_prompt", "input_tokens", "output_tokens", "cost_usd",
            "num_turns_actual", "on_approve", "on_decline", "decline_reason",
            "ensemble_id", "ensemble_role", "verify_cmd", "plan_id",
            "plan_step", "amend_count", "setup_cmd", "verification_failures",
            "verification_seconds", "blocked_by",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_dependencies_table_exists(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(dependencies)").fetchall()}
        assert cols == {"exploration_id", "depends_on_id"}

    def test_costs_table_exists(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(costs)").fetchall()}
        expected = {"id", "exploration_id", "operation", "model",
                    "input_tokens", "output_tokens", "cost_usd", "created_at"}
        assert expected.issubset(cols)

    def test_plans_table_exists(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(plans)").fetchall()}
        expected = {"id", "milestone_ref", "status", "plan_json", "created_at",
                    "completed_at", "total_cost_usd", "completion_note",
                    "prior_plan_json", "revision_count", "replan_trigger_step"}
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_external_blockers_table_exists(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(external_blockers)").fetchall()}
        expected = {"id", "description", "status", "created_at", "resolved_at"}
        assert expected.issubset(cols)

    def test_daemon_log_table_exists(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(daemon_log)").fetchall()}
        expected = {"id", "cycle_number", "started_at", "completed_at",
                    "harvested", "approved", "scheduled", "generated",
                    "audits", "cycle_cost_usd", "error"}
        assert expected.issubset(cols)

    def test_wal_mode_enabled(self, elmer_dir):
        """Database uses WAL journal mode for concurrent access."""
        conn = state.get_db(elmer_dir)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"

    def test_schema_idempotent(self, elmer_dir):
        """Calling get_db() twice on the same directory doesn't corrupt."""
        conn1 = state.get_db(elmer_dir)
        conn1.close()
        conn2 = state.get_db(elmer_dir)
        # Should still have all tables
        tables = {row[0] for row in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn2.close()
        assert "explorations" in tables
        assert "plans" in tables


# ---------------------------------------------------------------------------
# Exploration CRUD
# ---------------------------------------------------------------------------

class TestExplorationCRUD:
    """Verify create/read/update/delete round-trips for explorations."""

    def test_create_and_get(self, db):
        """create_exploration → get_exploration returns identical data."""
        state.create_exploration(
            db,
            id="exp-1",
            topic="Test topic",
            archetype="explore",
            branch="elmer/exp-1",
            worktree_path="/tmp/wt/exp-1",
            model="sonnet",
        )
        exp = state.get_exploration(db, "exp-1")
        assert exp is not None
        assert exp["id"] == "exp-1"
        assert exp["topic"] == "Test topic"
        assert exp["archetype"] == "explore"
        assert exp["branch"] == "elmer/exp-1"
        assert exp["model"] == "sonnet"
        assert exp["status"] == "running"

    def test_defaults(self, db):
        """New explorations have correct default values."""
        state.create_exploration(
            db,
            id="exp-d",
            topic="Defaults",
            archetype="explore",
            branch="elmer/exp-d",
            worktree_path="/tmp/wt/exp-d",
            model="sonnet",
        )
        exp = state.get_exploration(db, "exp-d")
        assert exp["amend_count"] == 0
        assert exp["verification_failures"] == 0
        assert exp["verification_seconds"] == 0
        assert exp["auto_approve"] == 0
        assert exp["generate_prompt"] == 0
        assert exp["cost_usd"] is None
        assert exp["pid"] is None
        assert exp["plan_id"] is None
        assert exp["ensemble_id"] is None

    def test_update(self, db):
        """update_exploration modifies specified fields only."""
        state.create_exploration(
            db,
            id="exp-u",
            topic="Update test",
            archetype="explore",
            branch="elmer/exp-u",
            worktree_path="/tmp/wt/exp-u",
            model="sonnet",
        )
        state.update_exploration(db, "exp-u", status="done", cost_usd=1.50)
        exp = state.get_exploration(db, "exp-u")
        assert exp["status"] == "done"
        assert exp["cost_usd"] == 1.50
        assert exp["topic"] == "Update test"  # unchanged

    def test_update_empty_kwargs_is_noop(self, db):
        """update_exploration with no kwargs doesn't error."""
        state.create_exploration(
            db,
            id="exp-noop",
            topic="Noop",
            archetype="explore",
            branch="elmer/exp-noop",
            worktree_path="/tmp/wt/exp-noop",
            model="sonnet",
        )
        state.update_exploration(db, "exp-noop")  # no kwargs
        exp = state.get_exploration(db, "exp-noop")
        assert exp["status"] == "running"

    def test_delete(self, db):
        """delete_exploration removes the exploration and its dependencies."""
        state.create_exploration(
            db,
            id="exp-del",
            topic="Delete test",
            archetype="explore",
            branch="elmer/exp-del",
            worktree_path="/tmp/wt/exp-del",
            model="sonnet",
        )
        state.create_exploration(
            db,
            id="exp-dep",
            topic="Dependent",
            archetype="explore",
            branch="elmer/exp-dep",
            worktree_path="/tmp/wt/exp-dep",
            model="sonnet",
        )
        state.add_dependency(db, "exp-dep", "exp-del")

        state.delete_exploration(db, "exp-del")
        assert state.get_exploration(db, "exp-del") is None
        assert state.get_dependencies(db, "exp-dep") == []

    def test_get_nonexistent_returns_none(self, db):
        assert state.get_exploration(db, "nonexistent") is None

    def test_list_explorations_all(self, db):
        """list_explorations with no filter returns all."""
        for i in range(3):
            state.create_exploration(
                db,
                id=f"exp-{i}",
                topic=f"Topic {i}",
                archetype="explore",
                branch=f"elmer/exp-{i}",
                worktree_path=f"/tmp/wt/exp-{i}",
                model="sonnet",
                status="running" if i < 2 else "done",
            )
        assert len(state.list_explorations(db)) == 3

    def test_list_explorations_by_status(self, db):
        """list_explorations with status filter returns matching only."""
        for i in range(3):
            state.create_exploration(
                db,
                id=f"exp-f{i}",
                topic=f"Topic {i}",
                archetype="explore",
                branch=f"elmer/exp-f{i}",
                worktree_path=f"/tmp/wt/exp-f{i}",
                model="sonnet",
                status="running" if i < 2 else "done",
            )
        assert len(state.list_explorations(db, status="running")) == 2
        assert len(state.list_explorations(db, status="done")) == 1


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

class TestDependencies:
    """Verify dependency CRUD and cycle detection."""

    def _make_exp(self, db, exp_id, status="running"):
        state.create_exploration(
            db, id=exp_id, topic=f"T-{exp_id}", archetype="explore",
            branch=f"elmer/{exp_id}", worktree_path=f"/tmp/wt/{exp_id}",
            model="sonnet", status=status,
        )

    def test_add_and_get(self, db):
        self._make_exp(db, "a")
        self._make_exp(db, "b")
        state.add_dependency(db, "b", "a")
        assert state.get_dependencies(db, "b") == ["a"]
        assert state.get_dependents(db, "a") == ["b"]

    def test_duplicate_dependency_ignored(self, db):
        """INSERT OR IGNORE prevents duplicate dependency entries."""
        self._make_exp(db, "a")
        self._make_exp(db, "b")
        state.add_dependency(db, "b", "a")
        state.add_dependency(db, "b", "a")  # duplicate
        assert state.get_dependencies(db, "b") == ["a"]

    def test_cycle_detection_simple(self, db):
        """Direct cycle: A→B, then B→A would create a cycle."""
        self._make_exp(db, "a")
        self._make_exp(db, "b")
        state.add_dependency(db, "b", "a")
        assert state.would_create_cycle(db, "a", "b") is True

    def test_cycle_detection_transitive(self, db):
        """Transitive cycle: A→B→C, then C→A would create a cycle."""
        self._make_exp(db, "a")
        self._make_exp(db, "b")
        self._make_exp(db, "c")
        state.add_dependency(db, "b", "a")
        state.add_dependency(db, "c", "b")
        assert state.would_create_cycle(db, "a", "c") is True

    def test_no_cycle_when_safe(self, db):
        """A→B, then C→A is not a cycle."""
        self._make_exp(db, "a")
        self._make_exp(db, "b")
        self._make_exp(db, "c")
        state.add_dependency(db, "b", "a")
        assert state.would_create_cycle(db, "c", "a") is False

    def test_pending_ready(self, db):
        """get_pending_ready returns pending explorations with all deps approved."""
        self._make_exp(db, "a", status="approved")
        self._make_exp(db, "b", status="pending")
        state.add_dependency(db, "b", "a")
        ready = state.get_pending_ready(db)
        assert len(ready) == 1
        assert ready[0]["id"] == "b"

    def test_pending_not_ready(self, db):
        """Pending exploration with running dependency is not ready."""
        self._make_exp(db, "a", status="running")
        self._make_exp(db, "b", status="pending")
        state.add_dependency(db, "b", "a")
        assert state.get_pending_ready(db) == []

    def test_pending_blocked(self, db):
        """get_pending_blocked returns pending with failed/declined deps."""
        self._make_exp(db, "a", status="failed")
        self._make_exp(db, "b", status="pending")
        state.add_dependency(db, "b", "a")
        blocked = state.get_pending_blocked(db)
        assert len(blocked) == 1
        assert blocked[0]["id"] == "b"


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

class TestPlanCRUD:
    """Verify plan create/read/update round-trips."""

    def test_create_and_get(self, db):
        plan_json = json.dumps({"milestone": "test", "steps": [{"topic": "A"}]})
        state.create_plan(db, id="plan-1", milestone_ref="test", plan_json=plan_json)
        plan = state.get_plan(db, "plan-1")
        assert plan is not None
        assert plan["milestone_ref"] == "test"
        assert plan["status"] == "active"
        assert plan["revision_count"] == 0
        assert plan["total_cost_usd"] == 0

    def test_update_plan(self, db):
        plan_json = json.dumps({"milestone": "test", "steps": []})
        state.create_plan(db, id="plan-u", milestone_ref="test", plan_json=plan_json)
        state.update_plan(db, "plan-u", status="completed", total_cost_usd=5.0)
        plan = state.get_plan(db, "plan-u")
        assert plan["status"] == "completed"
        assert plan["total_cost_usd"] == 5.0

    def test_list_plans(self, db):
        for i in range(3):
            pj = json.dumps({"milestone": f"m{i}", "steps": []})
            state.create_plan(db, id=f"plan-{i}", milestone_ref=f"m{i}", plan_json=pj)
        state.update_plan(db, "plan-2", status="completed")
        assert len(state.list_plans(db)) == 3
        assert len(state.list_plans(db, status="active")) == 2
        assert len(state.list_plans(db, status="completed")) == 1

    def test_get_plan_explorations(self, db):
        pj = json.dumps({"milestone": "test", "steps": [{"topic": "A"}, {"topic": "B"}]})
        state.create_plan(db, id="plan-e", milestone_ref="test", plan_json=pj)
        for i in range(2):
            state.create_exploration(
                db, id=f"step-{i}", topic=f"Step {i}", archetype="implement",
                branch=f"elmer/step-{i}", worktree_path=f"/tmp/wt/step-{i}",
                model="sonnet", plan_id="plan-e", plan_step=i,
            )
        exps = state.get_plan_explorations(db, "plan-e")
        assert len(exps) == 2
        assert exps[0]["plan_step"] == 0
        assert exps[1]["plan_step"] == 1

    def test_get_nonexistent_plan(self, db):
        assert state.get_plan(db, "nope") is None


# ---------------------------------------------------------------------------
# Costs
# ---------------------------------------------------------------------------

class TestCostCRUD:
    """Verify cost recording and retrieval."""

    def test_record_and_list(self, db):
        state.record_meta_cost(
            db, operation="generate", model="sonnet",
            input_tokens=100, output_tokens=50, cost_usd=0.03,
        )
        costs = state.get_all_costs(db)
        assert len(costs) == 1
        assert costs[0]["operation"] == "generate"
        assert costs[0]["cost_usd"] == 0.03

    def test_null_cost_recorded(self, db):
        """cost_usd=None is stored as NULL, not 0."""
        state.record_meta_cost(
            db, operation="test", model="sonnet",
            cost_usd=None,
        )
        costs = state.get_all_costs(db)
        assert costs[0]["cost_usd"] is None


# ---------------------------------------------------------------------------
# External blockers
# ---------------------------------------------------------------------------

class TestBlockerCRUD:
    """Verify external blocker create/resolve/list."""

    def test_create_and_get(self, db):
        state.create_blocker(db, id="blk-1", description="Waiting for review")
        blk = state.get_blocker(db, "blk-1")
        assert blk["status"] == "blocked"
        assert blk["description"] == "Waiting for review"

    def test_resolve(self, db):
        state.create_blocker(db, id="blk-r", description="Test")
        assert state.resolve_blocker(db, "blk-r") is True
        blk = state.get_blocker(db, "blk-r")
        assert blk["status"] == "resolved"
        assert blk["resolved_at"] is not None

    def test_resolve_nonexistent(self, db):
        assert state.resolve_blocker(db, "nope") is False

    def test_resolve_idempotent(self, db):
        """Resolving an already-resolved blocker returns False."""
        state.create_blocker(db, id="blk-i", description="Test")
        state.resolve_blocker(db, "blk-i")
        assert state.resolve_blocker(db, "blk-i") is False

    def test_list_by_status(self, db):
        state.create_blocker(db, id="b1", description="A")
        state.create_blocker(db, id="b2", description="B")
        state.resolve_blocker(db, "b1")
        assert len(state.list_blockers(db, status="blocked")) == 1
        assert len(state.list_blockers(db, status="resolved")) == 1
        assert len(state.list_blockers(db)) == 2


# ---------------------------------------------------------------------------
# Ensemble helpers
# ---------------------------------------------------------------------------

class TestEnsembleHelpers:
    """Verify ensemble query helpers."""

    def _make_replica(self, db, exp_id, ensemble_id, status="done"):
        state.create_exploration(
            db, id=exp_id, topic="Replica", archetype="explore",
            branch=f"elmer/{exp_id}", worktree_path=f"/tmp/wt/{exp_id}",
            model="sonnet", status=status,
            ensemble_id=ensemble_id, ensemble_role="replica",
        )

    def _make_synthesis(self, db, exp_id, ensemble_id, status="running"):
        state.create_exploration(
            db, id=exp_id, topic="Synthesis", archetype="explore",
            branch=f"elmer/{exp_id}", worktree_path=f"/tmp/wt/{exp_id}",
            model="sonnet", status=status,
            ensemble_id=ensemble_id, ensemble_role="synthesis",
        )

    def test_get_replicas(self, db):
        self._make_replica(db, "r1", "ens-1")
        self._make_replica(db, "r2", "ens-1")
        replicas = state.get_ensemble_replicas(db, "ens-1")
        assert len(replicas) == 2

    def test_get_synthesis(self, db):
        self._make_synthesis(db, "syn-1", "ens-1")
        syn = state.get_ensemble_synthesis(db, "ens-1")
        assert syn is not None
        assert syn["ensemble_role"] == "synthesis"

    def test_ready_ensemble(self, db):
        """Ensemble is ready when all replicas done and no synthesis exists."""
        self._make_replica(db, "r1", "ens-r", status="done")
        self._make_replica(db, "r2", "ens-r", status="done")
        ready = state.get_ready_ensembles(db)
        assert "ens-r" in ready

    def test_not_ready_if_replica_running(self, db):
        self._make_replica(db, "r1", "ens-nr", status="done")
        self._make_replica(db, "r2", "ens-nr", status="running")
        assert "ens-nr" not in state.get_ready_ensembles(db)

    def test_not_ready_if_synthesis_exists(self, db):
        self._make_replica(db, "r1", "ens-s", status="done")
        self._make_synthesis(db, "syn", "ens-s")
        assert "ens-s" not in state.get_ready_ensembles(db)

    def test_ensemble_status_running(self, db):
        self._make_replica(db, "r1", "ens-st", status="running")
        assert state.get_ensemble_status(db, "ens-st") == "running"

    def test_ensemble_status_approved(self, db):
        self._make_replica(db, "r1", "ens-ap", status="done")
        self._make_synthesis(db, "syn", "ens-ap", status="approved")
        assert state.get_ensemble_status(db, "ens-ap") == "approved"


# ---------------------------------------------------------------------------
# Increment helpers
# ---------------------------------------------------------------------------

class TestIncrementHelpers:
    """Verify amend_count and verification_failures increment correctly."""

    def _make_exp(self, db, exp_id):
        state.create_exploration(
            db, id=exp_id, topic="Test", archetype="explore",
            branch=f"elmer/{exp_id}", worktree_path=f"/tmp/wt/{exp_id}",
            model="sonnet",
        )

    def test_increment_amend_count(self, db):
        self._make_exp(db, "inc-a")
        assert state.increment_amend_count(db, "inc-a") == 1
        assert state.increment_amend_count(db, "inc-a") == 2

    def test_increment_amend_nonexistent(self, db):
        assert state.increment_amend_count(db, "nope") == 0


# ---------------------------------------------------------------------------
# State invariant checks (ADR-075)
# ---------------------------------------------------------------------------

class TestCheckStateInvariants:
    """Verify check_state_invariants() catches consistency violations."""

    def _make_exp(self, db, exp_id, **kwargs):
        defaults = dict(
            topic="Test", archetype="explore",
            branch=f"elmer/{exp_id}", worktree_path=f"/tmp/wt/{exp_id}",
            model="sonnet",
        )
        defaults.update(kwargs)
        state.create_exploration(db, id=exp_id, **defaults)

    def test_clean_state_passes(self, db):
        """A fresh database with valid data has no violations."""
        self._make_exp(db, "a")
        assert state.check_state_invariants(db) == []

    def test_plan_id_without_plan_step(self, db):
        """Exploration with plan_id but NULL plan_step is a violation."""
        self._make_exp(db, "bad", plan_id="plan-1")
        # plan_step defaults to NULL when not set via create_exploration
        violations = state.check_state_invariants(db)
        assert any("NULL plan_step" in v for v in violations)

    def test_orphaned_dependency(self, db):
        """Dependency referencing nonexistent exploration is a violation."""
        self._make_exp(db, "a")
        # Insert a dependency pointing to a nonexistent exploration
        db.execute(
            "INSERT INTO dependencies (exploration_id, depends_on_id) VALUES (?, ?)",
            ("a", "ghost"),
        )
        db.commit()
        violations = state.check_state_invariants(db)
        assert any("nonexistent exploration" in v for v in violations)

    def test_orphaned_plan_reference(self, db):
        """Exploration referencing nonexistent plan is a violation."""
        self._make_exp(db, "orphan", plan_id="no-plan", plan_step=0)
        violations = state.check_state_invariants(db)
        assert any("nonexistent plan" in v for v in violations)

    def test_completed_plan_with_failed_step(self, db):
        """Completed plan with non-approved steps is a violation."""
        plan_json = json.dumps({"milestone": "test", "steps": [{"topic": "A"}]})
        state.create_plan(db, id="plan-bad", milestone_ref="test", plan_json=plan_json)
        state.update_plan(db, "plan-bad", status="completed")
        self._make_exp(db, "s0", plan_id="plan-bad", plan_step=0, status="failed")
        violations = state.check_state_invariants(db)
        assert any("non-approved step" in v for v in violations)

    def test_no_false_positive_on_valid_plan(self, db):
        """Completed plan with all approved steps has no violations."""
        plan_json = json.dumps({"milestone": "test", "steps": [{"topic": "A"}]})
        state.create_plan(db, id="plan-ok", milestone_ref="test", plan_json=plan_json)
        state.update_plan(db, "plan-ok", status="completed")
        self._make_exp(db, "s0", plan_id="plan-ok", plan_step=0, status="approved")
        violations = state.check_state_invariants(db)
        assert violations == []
