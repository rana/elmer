"""Tests for stale pending exploration cleanup (ADR-058 / F1).

Verifies that pending explorations past their TTL are auto-cancelled
during schedule_ready(), and that fresh pending explorations are unaffected.
"""

from datetime import datetime, timezone, timedelta

import pytest

from elmer import state


@pytest.fixture
def elmer_dir(tmp_path):
    """Override: writes a config with a short TTL for stale-pending tests."""
    d = tmp_path / ".elmer"
    d.mkdir()
    (d / "logs").mkdir()
    config_path = d / "config.toml"
    config_path.write_text('[session]\npending_ttl_days = 1\n')
    return d


def _create_pending(db, exp_id, created_at=None):
    """Helper: create a pending exploration with an explicit created_at."""
    state.create_exploration(
        db,
        id=exp_id,
        topic=f"Test {exp_id}",
        archetype="explore",
        branch=f"elmer/{exp_id}",
        worktree_path=f"/tmp/wt/{exp_id}",
        model="sonnet",
        status="pending",
    )
    if created_at:
        db.execute(
            "UPDATE explorations SET created_at = ? WHERE id = ?",
            (created_at, exp_id),
        )
        db.commit()


class TestGetStalePending:
    """Tests for state.get_stale_pending()."""

    def test_fresh_pending_not_stale(self, db):
        """Pending exploration created just now is not stale."""
        _create_pending(db, "fresh-1")
        stale = state.get_stale_pending(db, max_age_hours=24)
        assert len(stale) == 0

    def test_old_pending_is_stale(self, db):
        """Pending exploration older than TTL is stale."""
        old_time = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        _create_pending(db, "old-1", created_at=old_time)
        stale = state.get_stale_pending(db, max_age_hours=24)
        assert len(stale) == 1
        assert stale[0]["id"] == "old-1"

    def test_running_not_affected(self, db):
        """Running explorations are never in stale pending results."""
        old_time = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        state.create_exploration(
            db,
            id="running-1",
            topic="Test",
            archetype="explore",
            branch="elmer/running-1",
            worktree_path="/tmp/wt/running-1",
            model="sonnet",
            status="running",
        )
        db.execute(
            "UPDATE explorations SET created_at = ? WHERE id = ?",
            (old_time, "running-1"),
        )
        db.commit()
        stale = state.get_stale_pending(db, max_age_hours=24)
        assert len(stale) == 0

    def test_mixed_fresh_and_stale(self, db):
        """Only stale pending explorations are returned."""
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        _create_pending(db, "old-1", created_at=old_time)
        _create_pending(db, "fresh-1")  # created now

        stale = state.get_stale_pending(db, max_age_hours=24)
        assert len(stale) == 1
        assert stale[0]["id"] == "old-1"


class TestScheduleReadyStalePending:
    """Integration test: schedule_ready auto-cancels stale pending."""

    def test_stale_pending_auto_cancelled(self, elmer_dir, db):
        """Stale pending explorations are marked failed by schedule_ready."""
        old_time = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        _create_pending(db, "stale-1", created_at=old_time)
        db.close()

        from elmer.explore import schedule_ready
        project_dir = elmer_dir.parent
        schedule_ready(elmer_dir, project_dir)

        conn = state.get_db(elmer_dir)
        exp = state.get_exploration(conn, "stale-1")
        conn.close()
        assert exp["status"] == "failed"
        assert "auto-cancelled" in exp["proposal_summary"]

    def test_fresh_pending_not_cancelled(self, elmer_dir, db):
        """Fresh pending explorations survive schedule_ready.

        We add a running dependency so the fresh pending isn't launched
        (which would require a real git repo).
        """
        # Create a running exploration as a dependency
        state.create_exploration(
            db,
            id="dep-1",
            topic="Dependency",
            archetype="explore",
            branch="elmer/dep-1",
            worktree_path="/tmp/wt/dep-1",
            model="sonnet",
            status="running",
        )
        _create_pending(db, "fresh-1")
        state.add_dependency(db, "fresh-1", "dep-1")
        db.close()

        from elmer.explore import schedule_ready
        project_dir = elmer_dir.parent
        schedule_ready(elmer_dir, project_dir)

        conn = state.get_db(elmer_dir)
        exp = state.get_exploration(conn, "fresh-1")
        conn.close()
        assert exp["status"] == "pending"
