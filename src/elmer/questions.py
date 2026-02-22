"""Question mining — extract open questions from project documentation.

Uses AI to parse CONTEXT.md, DESIGN.md, ROADMAP.md, DECISIONS.md for
explicit questions and implicit gaps. Clusters them by theme.
"""

import re
from pathlib import Path
from typing import Optional

from . import config, state, worker


def mine_questions(
    *,
    elmer_dir: Path,
    project_dir: Path,
    model: str = "sonnet",
    max_turns: int = 5,
) -> dict[str, list[str]]:
    """Mine open questions from project documentation.

    Returns dict mapping cluster name -> list of question strings.
    """
    if not worker.check_claude_available():
        raise RuntimeError(
            "claude CLI not found in PATH. Install Claude Code first."
        )

    # Load archetype
    template_path = config.resolve_archetype(elmer_dir, "mine-questions")
    template = template_path.read_text()

    # Run claude synchronously — it reads the project docs itself
    result = worker.run_claude(
        prompt=template,
        cwd=project_dir,
        model=model,
        max_turns=max_turns,
    )

    # Record meta-operation cost
    conn = state.get_db(elmer_dir)
    state.record_meta_cost(
        conn,
        operation="mine_questions",
        model=model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
    )
    conn.close()

    clusters = _parse_clusters(result.output)
    if not clusters:
        raise RuntimeError(
            f"Failed to parse question clusters from claude output:\n{result.output}"
        )

    return clusters


def _parse_clusters(output: str) -> dict[str, list[str]]:
    """Parse CLUSTER: <name> / - <question> format from claude output."""
    clusters: dict[str, list[str]] = {}
    current_cluster = None

    for line in output.splitlines():
        line = line.strip()

        # Match cluster header
        cluster_match = re.match(r"^CLUSTER:\s*(.+)$", line, re.IGNORECASE)
        if cluster_match:
            current_cluster = cluster_match.group(1).strip()
            clusters[current_cluster] = []
            continue

        # Match question line
        if current_cluster is not None and line.startswith("- "):
            question = line[2:].strip()
            if question:
                clusters[current_cluster].append(question)

    # Remove empty clusters
    return {k: v for k, v in clusters.items() if v}


def clusters_to_topics(
    clusters: dict[str, list[str]],
    cluster_filter: Optional[str] = None,
    max_per_cluster: int = 3,
) -> list[str]:
    """Convert question clusters into exploration topics.

    If cluster_filter is given, only questions from that cluster are used.
    Returns list of topic strings suitable for elmer explore.
    """
    topics = []

    for name, questions in clusters.items():
        if cluster_filter and cluster_filter.lower() not in name.lower():
            continue
        # Take up to max_per_cluster questions per cluster
        for q in questions[:max_per_cluster]:
            # Convert question to exploration topic
            topic = q.rstrip("?").strip()
            topics.append(topic)

    return topics
