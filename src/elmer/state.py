"""SQLite state management for explorations."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_NAME = "state.db"


def get_db(elmer_dir: Path) -> sqlite3.Connection:
    db_path = elmer_dir / DB_NAME
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS explorations (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            archetype TEXT NOT NULL,
            branch TEXT NOT NULL,
            worktree_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            model TEXT NOT NULL DEFAULT 'sonnet',
            pid INTEGER,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            merged_at TEXT,
            proposal_summary TEXT,
            parent_id TEXT,
            max_turns INTEGER,
            auto_approve INTEGER DEFAULT 0,
            generate_prompt INTEGER DEFAULT 0
        )
    """)

    # Migrate existing DBs: add columns that may not exist yet
    for col, coltype in [("parent_id", "TEXT"), ("max_turns", "INTEGER"),
                         ("auto_approve", "INTEGER DEFAULT 0"),
                         ("generate_prompt", "INTEGER DEFAULT 0"),
                         ("input_tokens", "INTEGER"),
                         ("output_tokens", "INTEGER"),
                         ("cost_usd", "REAL"),
                         ("num_turns_actual", "INTEGER"),
                         ("on_approve", "TEXT"),
                         ("on_decline", "TEXT"),
                         ("decline_reason", "TEXT"),
                         ("ensemble_id", "TEXT"),
                         ("ensemble_role", "TEXT"),
                         ("verify_cmd", "TEXT"),
                         ("plan_id", "TEXT"),
                         ("plan_step", "INTEGER"),
                         ("amend_count", "INTEGER DEFAULT 0"),
                         ("setup_cmd", "TEXT"),
                         ("verification_failures", "INTEGER DEFAULT 0"),
                         ("verification_seconds", "REAL DEFAULT 0"),
                         ("blocked_by", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE explorations ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Migrate legacy column name: on_reject -> on_decline (ADR-027)
    try:
        conn.execute("ALTER TABLE explorations RENAME COLUMN on_reject TO on_decline")
    except sqlite3.OperationalError:
        pass  # Column already renamed or never existed

    # Migrate legacy status value: rejected -> declined (ADR-027)
    conn.execute("UPDATE explorations SET status = 'declined' WHERE status = 'rejected'")


    # Migrate plans table: add completion_note column (ADR-044)
    try:
        conn.execute("ALTER TABLE plans ADD COLUMN completion_note TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Migrate plans table: add revision tracking columns (ADR-067)
    for col, coltype in [("prior_plan_json", "TEXT"),
                         ("revision_count", "INTEGER DEFAULT 0"),
                         ("replan_trigger_step", "INTEGER")]:
        try:
            conn.execute(f"ALTER TABLE plans ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.execute("""
        CREATE TABLE IF NOT EXISTS dependencies (
            exploration_id TEXT NOT NULL,
            depends_on_id TEXT NOT NULL,
            PRIMARY KEY (exploration_id, depends_on_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exploration_id TEXT,
            operation TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_usd REAL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY,
            milestone_ref TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            plan_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            total_cost_usd REAL DEFAULT 0,
            completion_note TEXT,
            prior_plan_json TEXT,
            revision_count INTEGER DEFAULT 0,
            replan_trigger_step INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS external_blockers (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'blocked',
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS daemon_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_number INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            harvested INTEGER DEFAULT 0,
            approved INTEGER DEFAULT 0,
            scheduled INTEGER DEFAULT 0,
            generated INTEGER DEFAULT 0,
            audits INTEGER DEFAULT 0,
            cycle_cost_usd REAL,
            error TEXT
        )
    """)

    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_exploration(
    conn: sqlite3.Connection,
    *,
    id: str,
    topic: str,
    archetype: str,
    branch: str,
    worktree_path: str,
    model: str,
    pid: Optional[int] = None,
    status: str = "running",
    parent_id: Optional[str] = None,
    max_turns: Optional[int] = None,
    auto_approve: bool = False,
    generate_prompt: bool = False,
    on_approve: Optional[str] = None,
    on_decline: Optional[str] = None,
    ensemble_id: Optional[str] = None,
    ensemble_role: Optional[str] = None,
    verify_cmd: Optional[str] = None,
    plan_id: Optional[str] = None,
    plan_step: Optional[int] = None,
    setup_cmd: Optional[str] = None,
    blocked_by: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO explorations
            (id, topic, archetype, branch, worktree_path, status, model, pid,
             created_at, parent_id, max_turns, auto_approve, generate_prompt,
             on_approve, on_decline, ensemble_id, ensemble_role,
             verify_cmd, plan_id, plan_step, setup_cmd, blocked_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (id, topic, archetype, branch, worktree_path, status, model, pid,
         _now(), parent_id, max_turns, int(auto_approve), int(generate_prompt),
         on_approve, on_decline, ensemble_id, ensemble_role,
         verify_cmd, plan_id, plan_step, setup_cmd, blocked_by),
    )
    conn.commit()


def get_exploration(conn: sqlite3.Connection, exploration_id: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM explorations WHERE id = ?", (exploration_id,)
    ).fetchone()


def list_explorations(
    conn: sqlite3.Connection, status: Optional[str] = None
) -> list[sqlite3.Row]:
    if status:
        return conn.execute(
            "SELECT * FROM explorations WHERE status = ? ORDER BY created_at",
            (status,),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM explorations ORDER BY created_at"
    ).fetchall()


def update_exploration(conn: sqlite3.Connection, exploration_id: str, **kwargs) -> None:
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [exploration_id]
    conn.execute(f"UPDATE explorations SET {sets} WHERE id = ?", values)
    conn.commit()


def delete_exploration(conn: sqlite3.Connection, exploration_id: str) -> None:
    conn.execute("DELETE FROM dependencies WHERE exploration_id = ?", (exploration_id,))
    conn.execute("DELETE FROM dependencies WHERE depends_on_id = ?", (exploration_id,))
    conn.execute("DELETE FROM explorations WHERE id = ?", (exploration_id,))
    conn.commit()


# --- Dependency CRUD ---


def add_dependency(conn: sqlite3.Connection, exploration_id: str, depends_on_id: str) -> None:
    """Record that exploration_id depends on depends_on_id."""
    conn.execute(
        "INSERT OR IGNORE INTO dependencies (exploration_id, depends_on_id) VALUES (?, ?)",
        (exploration_id, depends_on_id),
    )
    conn.commit()


def get_dependencies(conn: sqlite3.Connection, exploration_id: str) -> list[str]:
    """Get IDs that this exploration depends on."""
    rows = conn.execute(
        "SELECT depends_on_id FROM dependencies WHERE exploration_id = ?",
        (exploration_id,),
    ).fetchall()
    return [r["depends_on_id"] for r in rows]


def get_dependents(conn: sqlite3.Connection, exploration_id: str) -> list[str]:
    """Get IDs that depend on this exploration."""
    rows = conn.execute(
        "SELECT exploration_id FROM dependencies WHERE depends_on_id = ?",
        (exploration_id,),
    ).fetchall()
    return [r["exploration_id"] for r in rows]


def would_create_cycle(conn: sqlite3.Connection, exploration_id: str, depends_on_id: str) -> bool:
    """Check if adding exploration_id -> depends_on_id would create a cycle.

    Returns True if depends_on_id already transitively depends on exploration_id,
    meaning that adding this edge would close a loop.
    """
    # DFS from depends_on_id through existing dependencies.
    # If we can reach exploration_id, adding the edge creates a cycle.
    visited: set[str] = set()
    stack = [depends_on_id]
    while stack:
        current = stack.pop()
        if current == exploration_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(get_dependencies(conn, current))
    return False


def get_pending_ready(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Get pending explorations whose dependencies are all approved."""
    return conn.execute("""
        SELECT e.* FROM explorations e
        WHERE e.status = 'pending'
        AND NOT EXISTS (
            SELECT 1 FROM dependencies d
            JOIN explorations dep ON dep.id = d.depends_on_id
            WHERE d.exploration_id = e.id AND dep.status != 'approved'
        )
    """).fetchall()


def get_stale_pending(conn: sqlite3.Connection, max_age_hours: float) -> list[sqlite3.Row]:
    """Get pending explorations older than max_age_hours.

    These explorations have been waiting for dependencies that may never
    resolve. The caller should auto-cancel them to free resources (ADR-058).
    """
    return conn.execute(
        """
        SELECT * FROM explorations
        WHERE status = 'pending'
        AND created_at < datetime('now', '-' || ? || ' hours')
        ORDER BY created_at
        """,
        (max_age_hours,),
    ).fetchall()


def get_pending_blocked(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Get pending explorations that have at least one failed or declined dependency.

    These can never become ready — their dependencies are permanently unresolvable.
    The caller should cascade the failure (mark them as failed too).
    """
    return conn.execute("""
        SELECT DISTINCT e.* FROM explorations e
        JOIN dependencies d ON d.exploration_id = e.id
        JOIN explorations dep ON dep.id = d.depends_on_id
        WHERE e.status = 'pending'
        AND dep.status IN ('failed', 'declined')
    """).fetchall()


# --- Cost CRUD ---


def record_meta_cost(
    conn: sqlite3.Connection,
    *,
    operation: str,
    model: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
    exploration_id: Optional[str] = None,
) -> None:
    """Record the cost of a meta-operation (generate, auto_approve, prompt_gen)."""
    conn.execute(
        """
        INSERT INTO costs (exploration_id, operation, model, input_tokens,
                           output_tokens, cost_usd, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (exploration_id, operation, model, input_tokens, output_tokens,
         cost_usd, _now()),
    )
    conn.commit()


def get_all_costs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Get all meta-operation cost records."""
    return conn.execute(
        "SELECT * FROM costs ORDER BY created_at"
    ).fetchall()


# --- Ensemble helpers ---


def get_ensemble_replicas(conn: sqlite3.Connection, ensemble_id: str) -> list[sqlite3.Row]:
    """Get all replicas for an ensemble (excludes synthesis)."""
    return conn.execute(
        "SELECT * FROM explorations WHERE ensemble_id = ? AND ensemble_role = 'replica' ORDER BY created_at",
        (ensemble_id,),
    ).fetchall()


def get_ensemble_synthesis(conn: sqlite3.Connection, ensemble_id: str) -> Optional[sqlite3.Row]:
    """Get the synthesis exploration for an ensemble, if it exists."""
    return conn.execute(
        "SELECT * FROM explorations WHERE ensemble_id = ? AND ensemble_role = 'synthesis'",
        (ensemble_id,),
    ).fetchone()


def get_ready_ensembles(conn: sqlite3.Connection) -> list[str]:
    """Get ensemble IDs where all replicas are done/failed but no synthesis exists yet.

    An ensemble is ready to synthesize when:
    - All replicas have finished (done or failed)
    - At least one replica succeeded (done)
    - No synthesis exploration exists yet
    """
    rows = conn.execute("""
        SELECT DISTINCT e.ensemble_id
        FROM explorations e
        WHERE e.ensemble_id IS NOT NULL
          AND e.ensemble_role = 'replica'
          AND NOT EXISTS (
              SELECT 1 FROM explorations s
              WHERE s.ensemble_id = e.ensemble_id AND s.ensemble_role = 'synthesis'
          )
        GROUP BY e.ensemble_id
        HAVING COUNT(*) = SUM(CASE WHEN e.status IN ('done', 'failed') THEN 1 ELSE 0 END)
           AND SUM(CASE WHEN e.status = 'done' THEN 1 ELSE 0 END) > 0
    """).fetchall()
    return [r["ensemble_id"] for r in rows]


def get_ensemble_status(conn: sqlite3.Connection, ensemble_id: str) -> str:
    """Derive ensemble status from component explorations."""
    synthesis = get_ensemble_synthesis(conn, ensemble_id)
    if synthesis:
        if synthesis["status"] == "approved":
            return "approved"
        if synthesis["status"] == "declined":
            return "declined"
        if synthesis["status"] == "done":
            return "review"
        if synthesis["status"] in ("running", "amending"):
            return "synthesizing"
        if synthesis["status"] == "failed":
            return "failed"

    replicas = get_ensemble_replicas(conn, ensemble_id)
    if not replicas:
        return "unknown"
    if all(r["status"] in ("done", "failed") for r in replicas):
        if any(r["status"] == "done" for r in replicas):
            return "ready"
        return "failed"
    if any(r["status"] == "running" for r in replicas):
        return "running"
    return "pending"


# --- Plan CRUD ---


def create_plan(
    conn: sqlite3.Connection,
    *,
    id: str,
    milestone_ref: str,
    plan_json: str,
) -> None:
    """Create an implementation plan."""
    conn.execute(
        "INSERT INTO plans (id, milestone_ref, plan_json, created_at) VALUES (?, ?, ?, ?)",
        (id, milestone_ref, plan_json, _now()),
    )
    conn.commit()


def get_plan(conn: sqlite3.Connection, plan_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()


def list_plans(conn: sqlite3.Connection, status: Optional[str] = None) -> list[sqlite3.Row]:
    if status:
        return conn.execute(
            "SELECT * FROM plans WHERE status = ? ORDER BY created_at", (status,)
        ).fetchall()
    return conn.execute("SELECT * FROM plans ORDER BY created_at").fetchall()


def update_plan(conn: sqlite3.Connection, plan_id: str, **kwargs) -> None:
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [plan_id]
    conn.execute(f"UPDATE plans SET {sets} WHERE id = ?", values)
    conn.commit()


def get_plan_explorations(conn: sqlite3.Connection, plan_id: str) -> list[sqlite3.Row]:
    """Get all explorations belonging to a plan, ordered by step number."""
    return conn.execute(
        "SELECT * FROM explorations WHERE plan_id = ? ORDER BY plan_step",
        (plan_id,),
    ).fetchall()


def increment_amend_count(conn: sqlite3.Connection, exploration_id: str) -> int:
    """Increment and return the amend count for an exploration."""
    conn.execute(
        "UPDATE explorations SET amend_count = COALESCE(amend_count, 0) + 1 WHERE id = ?",
        (exploration_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT amend_count FROM explorations WHERE id = ?", (exploration_id,),
    ).fetchone()
    return row["amend_count"] if row else 0


def increment_verification_failures(conn: sqlite3.Connection, exploration_id: str) -> int:
    """Increment and return the verification failure count for an exploration."""
    conn.execute(
        "UPDATE explorations SET verification_failures = COALESCE(verification_failures, 0) + 1 WHERE id = ?",
        (exploration_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT verification_failures FROM explorations WHERE id = ?", (exploration_id,),
    ).fetchone()
    return row["verification_failures"] if row else 0


# --- External blockers (ADR-065) ---


def create_blocker(
    conn: sqlite3.Connection,
    *,
    id: str,
    description: str,
) -> None:
    """Create an external blocker (stakeholder decision, prerequisite, etc.)."""
    conn.execute(
        "INSERT OR IGNORE INTO external_blockers (id, description, status, created_at) VALUES (?, ?, 'blocked', ?)",
        (id, description, _now()),
    )
    conn.commit()


def resolve_blocker(conn: sqlite3.Connection, blocker_id: str) -> bool:
    """Mark an external blocker as resolved. Returns True if found."""
    result = conn.execute(
        "UPDATE external_blockers SET status = 'resolved', resolved_at = ? WHERE id = ? AND status = 'blocked'",
        (_now(), blocker_id),
    )
    conn.commit()
    return result.rowcount > 0


def get_blocker(conn: sqlite3.Connection, blocker_id: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM external_blockers WHERE id = ?", (blocker_id,)
    ).fetchone()


def list_blockers(conn: sqlite3.Connection, status: Optional[str] = None) -> list[sqlite3.Row]:
    if status:
        return conn.execute(
            "SELECT * FROM external_blockers WHERE status = ? ORDER BY created_at",
            (status,),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM external_blockers ORDER BY created_at"
    ).fetchall()


def get_externally_blocked(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Get pending explorations that reference unresolved external blockers.

    The blocked_by column contains a comma-separated list of blocker IDs.
    An exploration is externally blocked if ANY referenced blocker is still 'blocked'.
    """
    return conn.execute("""
        SELECT e.* FROM explorations e
        WHERE e.status = 'pending'
        AND e.blocked_by IS NOT NULL
        AND e.blocked_by != ''
        AND EXISTS (
            SELECT 1 FROM external_blockers b
            WHERE b.status = 'blocked'
            AND (',' || e.blocked_by || ',') LIKE ('%,' || b.id || ',%')
        )
    """).fetchall()
