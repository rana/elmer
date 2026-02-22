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
            proposal_summary TEXT
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
    pid: int,
) -> None:
    conn.execute(
        """
        INSERT INTO explorations
            (id, topic, archetype, branch, worktree_path, status, model, pid, created_at)
        VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?)
        """,
        (id, topic, archetype, branch, worktree_path, model, pid, _now()),
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
    conn.execute("DELETE FROM explorations WHERE id = ?", (exploration_id,))
    conn.commit()
