"""Cross-project insight log — extract and inject generalizable insights.

Insights are stored in ~/.elmer/insights.db, shared across all projects.
Extraction happens after exploration approval. Injection happens during
prompt assembly, adding relevant cross-project context.
"""

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config, state, worker

INSIGHTS_DB_NAME = "insights.db"


def _get_global_dir() -> Path:
    """Get or create ~/.elmer/ directory."""
    global_dir = Path.home() / ".elmer"
    global_dir.mkdir(exist_ok=True)
    return global_dir


def get_insights_db() -> sqlite3.Connection:
    """Open the global insights database."""
    global_dir = _get_global_dir()
    db_path = global_dir / INSIGHTS_DB_NAME
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            source_project TEXT,
            source_exploration TEXT,
            source_topic TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_insights(
    *,
    elmer_dir: Path,
    project_dir: Path,
    exploration_id: str,
    model: str = "sonnet",
    max_turns: int = 3,
) -> list[str]:
    """Extract generalizable insights from a completed exploration.

    Runs a synchronous claude session with the extract-insights archetype.
    Returns list of insight strings. Best-effort — failures return [].
    """
    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)
    conn.close()

    if exp is None:
        return []

    # Read proposal
    worktree_path = Path(exp["worktree_path"])
    proposal_path = worktree_path / "PROPOSAL.md"
    if not proposal_path.exists():
        return []

    proposal_text = proposal_path.read_text()
    if not proposal_text.strip():
        return []

    # Try agent-aware invocation, fall back to template substitution
    agent_config = config.resolve_meta_agent(project_dir, "extract-insights")

    if agent_config is not None:
        prompt = proposal_text
    else:
        try:
            template_path = config.resolve_archetype(elmer_dir, "extract-insights")
        except FileNotFoundError:
            return []
        template = template_path.read_text()
        prompt = template.replace("$PROPOSAL", proposal_text)

    # Run extraction
    try:
        result = worker.run_claude(
            prompt=prompt,
            cwd=project_dir,
            model=model,
            max_turns=max_turns,
            agent_config=agent_config,
        )
    except RuntimeError:
        return []

    # Record meta-operation cost
    conn = state.get_db(elmer_dir)
    state.record_meta_cost(
        conn,
        operation="extract_insights",
        model=model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        exploration_id=exploration_id,
    )
    conn.close()

    # Parse output
    insights = _parse_insights(result.output)

    # Store in global DB
    if insights:
        project_name = project_dir.name
        idb = get_insights_db()
        for text in insights:
            idb.execute(
                "INSERT INTO insights (text, source_project, source_exploration, "
                "source_topic, created_at) VALUES (?, ?, ?, ?, ?)",
                (text, project_name, exploration_id, exp["topic"], _now()),
            )
        idb.commit()
        idb.close()

    return insights


def _parse_insights(output: str) -> list[str]:
    """Parse numbered insight list from claude output."""
    if "NONE" in output.strip().upper().split("\n")[0]:
        return []
    insights = []
    for line in output.splitlines():
        match = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if match:
            text = match.group(1).strip()
            if text:
                insights.append(text)
    return insights


def get_relevant_insights(
    topic: str,
    project_name: Optional[str] = None,
    limit: int = 5,
) -> list[dict]:
    """Get insights relevant to a topic, optionally excluding a project.

    Uses simple keyword matching. Returns list of dicts with 'text',
    'source_project', 'source_topic'.
    """
    try:
        idb = get_insights_db()
    except Exception:
        return []

    rows = idb.execute(
        "SELECT text, source_project, source_exploration, source_topic "
        "FROM insights ORDER BY created_at DESC"
    ).fetchall()
    idb.close()

    if not rows:
        return []

    # Simple relevance scoring: count keyword overlap
    topic_words = set(topic.lower().split())
    # Remove common words
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                 "being", "have", "has", "had", "do", "does", "did", "will",
                 "would", "could", "should", "may", "might", "can", "shall",
                 "to", "of", "in", "for", "on", "with", "at", "by", "from",
                 "as", "into", "through", "during", "before", "after", "and",
                 "but", "or", "nor", "not", "so", "yet", "both", "either",
                 "neither", "each", "every", "all", "any", "few", "more",
                 "most", "other", "some", "such", "no", "only", "own",
                 "same", "than", "too", "very", "this", "that", "these",
                 "those", "it", "its"}
    topic_words -= stopwords

    scored = []
    for row in rows:
        # Optionally exclude insights from the same project
        if project_name and row["source_project"] == project_name:
            continue

        insight_words = set(row["text"].lower().split()) - stopwords
        overlap = len(topic_words & insight_words)
        if overlap > 0:
            scored.append((overlap, dict(row)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:limit]]


def format_insights_context(insights: list[dict]) -> str:
    """Format insights for injection into an exploration prompt."""
    if not insights:
        return ""

    lines = ["## Cross-Project Insights", "",
             "Relevant insights from other explorations:", ""]
    for ins in insights:
        source = ins.get("source_project", "unknown")
        lines.append(f"- {ins['text']} (from: {source})")
    lines.append("")
    return "\n".join(lines)


def list_all_insights() -> list[sqlite3.Row]:
    """List all stored insights."""
    try:
        idb = get_insights_db()
        rows = idb.execute(
            "SELECT * FROM insights ORDER BY created_at DESC"
        ).fetchall()
        idb.close()
        return rows
    except Exception:
        return []
