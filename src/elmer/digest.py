"""Digest synthesis — convergence across approved and declined explorations.

Reads the proposal archive and decline reasons, calls claude -p with
the digest meta-agent, and stores the result in .elmer/digests/.
Digests feed into topic generation and the daemon loop.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config, state, worker


def run_digest(
    *,
    elmer_dir: Path,
    project_dir: Path,
    model: str = "sonnet",
    max_turns: int = 5,
    since: Optional[str] = None,
    topic_filter: Optional[str] = None,
) -> Path:
    """Synthesize a digest from recent explorations. Returns path to digest file.

    Reads approved/declined proposals, assembles context, runs the digest
    meta-agent, and stores the result in .elmer/digests/.
    """
    if not worker.check_claude_available():
        raise RuntimeError(
            "claude CLI not found in PATH. Install Claude Code first."
        )

    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn)
    conn.close()

    # Build context sections
    history = _format_history(explorations)
    approved_text = _read_approved_proposals(elmer_dir, explorations, since=since, topic_filter=topic_filter)
    declined_text = _read_declined_proposals(explorations, since=since, topic_filter=topic_filter)
    previous_digest = _read_latest_digest(elmer_dir)

    # Build prompt
    agent_config = config.resolve_meta_agent(project_dir, "digest")

    if agent_config is not None:
        prompt = (
            f"Synthesize a convergence digest from the following exploration data.\n\n"
            f"## Exploration History\n\n{history or '(none yet)'}\n\n"
            f"## Approved Proposals\n\n{approved_text or '(none)'}\n\n"
            f"## Declined Proposals\n\n{declined_text or '(none)'}\n\n"
            f"## Previous Digest\n\n{previous_digest or '(first digest — no prior synthesis)'}"
        ).strip()
    else:
        template_path = config.resolve_archetype(elmer_dir, "digest")
        template = template_path.read_text()
        prompt = (
            template
            .replace("$HISTORY", history or "(none yet)")
            .replace("$APPROVED_PROPOSALS", approved_text or "(none)")
            .replace("$DECLINED_PROPOSALS", declined_text or "(none)")
            .replace("$PREVIOUS_DIGEST", previous_digest or "(first digest — no prior synthesis)")
        )

    result = worker.run_claude(
        prompt=prompt,
        cwd=project_dir,
        model=model,
        max_turns=max_turns,
        agent_config=agent_config,
    )

    # Record meta-operation cost
    conn = state.get_db(elmer_dir)
    state.record_meta_cost(
        conn,
        operation="digest",
        model=model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
    )
    conn.close()

    # Store the digest
    digest_path = _store_digest(elmer_dir, result.output)
    return digest_path


def get_latest_digest(elmer_dir: Path) -> Optional[str]:
    """Read the most recent digest file. Returns content or None."""
    return _read_latest_digest(elmer_dir)


def approvals_since_last_digest(elmer_dir: Path) -> int:
    """Count explorations approved since the most recent digest.

    Used by the daemon to decide when to trigger a synthesis cycle.
    Returns the count of approved explorations with merged_at after
    the latest digest timestamp, or total approved if no digest exists.
    """
    digests_dir = elmer_dir / "digests"
    if not digests_dir.exists():
        # No digests yet — count all approved
        conn = state.get_db(elmer_dir)
        count = conn.execute(
            "SELECT COUNT(*) FROM explorations WHERE status = 'approved'"
        ).fetchone()[0]
        conn.close()
        return count

    # Find the most recent digest by filename (ISO timestamp)
    digest_files = sorted(digests_dir.glob("digest-*.md"), reverse=True)
    if not digest_files:
        conn = state.get_db(elmer_dir)
        count = conn.execute(
            "SELECT COUNT(*) FROM explorations WHERE status = 'approved'"
        ).fetchone()[0]
        conn.close()
        return count

    # Extract timestamp from filename: digest-YYYY-MM-DDTHH-MM-SS.md
    latest_name = digest_files[0].stem  # digest-2026-02-23T14-30-00
    ts_part = latest_name.replace("digest-", "")
    # Convert filename timestamp back to ISO format
    last_digest_ts = ts_part.replace("-", ":", 2)  # Only first two dashes stay
    # More careful: the filename format is digest-YYYY-MM-DDTHH-MM-SS
    # We need to convert back to YYYY-MM-DDTHH:MM:SS
    parts = ts_part.split("T")
    if len(parts) == 2:
        date_part = parts[0]  # YYYY-MM-DD
        time_part = parts[1].replace("-", ":")  # HH:MM:SS
        last_digest_ts = f"{date_part}T{time_part}"
    else:
        last_digest_ts = ts_part

    conn = state.get_db(elmer_dir)
    count = conn.execute(
        "SELECT COUNT(*) FROM explorations WHERE status = 'approved' AND merged_at > ?",
        (last_digest_ts,),
    ).fetchone()[0]
    conn.close()
    return count


# --- Internal helpers ---


def _format_history(explorations: list) -> str:
    """Format all explorations as a status list for the prompt."""
    if not explorations:
        return ""
    lines = []
    for exp in explorations:
        reason = ""
        try:
            if exp["status"] == "declined" and exp["decline_reason"]:
                reason = f" (reason: {exp['decline_reason']})"
        except (IndexError, KeyError):
            pass
        lines.append(f"- [{exp['status']}] {exp['topic']}{reason}")
    return "\n".join(lines)


def _read_approved_proposals(
    elmer_dir: Path,
    explorations: list,
    *,
    since: Optional[str] = None,
    topic_filter: Optional[str] = None,
) -> str:
    """Read archived proposals for approved explorations."""
    proposals_dir = elmer_dir / "proposals"
    if not proposals_dir.exists():
        return ""

    sections = []
    for exp in explorations:
        if exp["status"] != "approved":
            continue
        if since and exp["merged_at"] and exp["merged_at"] < since:
            continue
        if topic_filter and topic_filter.lower() not in exp["topic"].lower():
            continue

        archive_path = proposals_dir / f"{exp['id']}.md"
        if archive_path.exists():
            content = archive_path.read_text()
            # Truncate very long proposals to keep prompt manageable
            if len(content) > 3000:
                content = content[:3000] + "\n\n[...truncated...]"
            sections.append(
                f"### {exp['topic']} ({exp['archetype']})\n\n{content}"
            )

    return "\n\n---\n\n".join(sections) if sections else ""


def _read_declined_proposals(
    explorations: list,
    *,
    since: Optional[str] = None,
    topic_filter: Optional[str] = None,
) -> str:
    """Format declined explorations with their reasons."""
    lines = []
    for exp in explorations:
        if exp["status"] != "declined":
            continue
        if since and exp.get("completed_at") and exp["completed_at"] < since:
            continue
        if topic_filter and topic_filter.lower() not in exp["topic"].lower():
            continue

        reason = ""
        try:
            reason = exp["decline_reason"] or ""
        except (IndexError, KeyError):
            pass

        if reason:
            lines.append(f"- **{exp['topic']}** — declined: {reason}")
        else:
            lines.append(f"- **{exp['topic']}** — declined (no reason recorded)")

    return "\n".join(lines) if lines else ""


def _read_latest_digest(elmer_dir: Path) -> Optional[str]:
    """Read the most recent digest file. Returns content or None."""
    digests_dir = elmer_dir / "digests"
    if not digests_dir.exists():
        return None

    digest_files = sorted(digests_dir.glob("digest-*.md"), reverse=True)
    if not digest_files:
        return None

    content = digest_files[0].read_text()
    # Truncate if very long to avoid prompt bloat
    if len(content) > 4000:
        content = content[:4000] + "\n\n[...truncated...]"
    return content


def _store_digest(elmer_dir: Path, content: str) -> Path:
    """Store a digest in .elmer/digests/ with a timestamped filename."""
    digests_dir = elmer_dir / "digests"
    digests_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    filename = f"digest-{now.strftime('%Y-%m-%dT%H-%M-%S')}.md"
    digest_path = digests_dir / filename

    # Prepend metadata header
    meta = (
        f"<!-- elmer:digest\n"
        f"  generated: {now.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"-->\n\n"
    )
    digest_path.write_text(meta + content)
    return digest_path
