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
                         ("budget_usd", "REAL"),
                         ("on_approve", "TEXT"),
                         ("on_decline", "TEXT")]:
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
    budget_usd: Optional[float] = None,
    on_approve: Optional[str] = None,
    on_decline: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO explorations
            (id, topic, archetype, branch, worktree_path, status, model, pid,
             created_at, parent_id, max_turns, auto_approve, generate_prompt,
             budget_usd, on_approve, on_decline)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (id, topic, archetype, branch, worktree_path, status, model, pid,
         _now(), parent_id, max_turns, int(auto_approve), int(generate_prompt),
         budget_usd, on_approve, on_decline),
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
