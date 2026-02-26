"""Digest synthesis — convergence across approved and declined explorations.

Reads the proposal archive and decline reasons, calls claude -p with
the digest meta-agent, and stores the result in .elmer/digests/.
Digests feed into topic generation and the daemon loop.

The archive is the source of truth for completed explorations (ADR-032).
After clean deletes DB records, the archive metadata (HTML comment header)
provides all fields needed for digest synthesis. The DB is still consulted
for in-flight explorations.
"""

import re
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

    # Build context from both DB (in-flight) and archive (completed)
    archived = _load_archived_proposals(elmer_dir)
    history = _format_history(explorations, archived)
    approved_text = _read_approved_proposals(elmer_dir, explorations, archived, since=since, topic_filter=topic_filter)
    declined_text = _read_declined_proposals(explorations, archived, since=since, topic_filter=topic_filter)
    previous_digest = _read_latest_digest(elmer_dir)

    # Build prompt
    agent_config = config.resolve_meta_agent(project_dir, "digest")

    prompt = (
        f"Synthesize a convergence digest from the following exploration data.\n\n"
        f"## Exploration History\n\n{history or '(none yet)'}\n\n"
        f"## Approved Proposals\n\n{approved_text or '(none)'}\n\n"
        f"## Declined Proposals\n\n{declined_text or '(none)'}\n\n"
        f"## Previous Digest\n\n{previous_digest or '(first digest — no prior synthesis)'}"
    ).strip()

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
    Checks both DB records and archive metadata (ADR-032) so that
    cleaned records are still counted.
    """
    last_digest_ts = _get_last_digest_timestamp(elmer_dir)

    # Count from DB (in-flight records)
    conn = state.get_db(elmer_dir)
    if last_digest_ts:
        db_count = conn.execute(
            "SELECT COUNT(*) FROM explorations WHERE status = 'approved' AND merged_at > ?",
            (last_digest_ts,),
        ).fetchone()[0]
    else:
        db_count = conn.execute(
            "SELECT COUNT(*) FROM explorations WHERE status = 'approved'"
        ).fetchone()[0]

    # Collect DB IDs to avoid double-counting
    db_ids = {r["id"] for r in conn.execute(
        "SELECT id FROM explorations WHERE status = 'approved'"
    ).fetchall()}
    conn.close()

    # Count from archive (cleaned records)
    archive_count = 0
    for meta in _load_archived_proposals(elmer_dir):
        if meta.get("id") in db_ids:
            continue
        if meta.get("status") != "approved":
            continue
        if last_digest_ts and meta.get("merged_at", meta.get("archived", "")) <= last_digest_ts:
            continue
        archive_count += 1

    return db_count + archive_count


def _get_last_digest_timestamp(elmer_dir: Path) -> Optional[str]:
    """Extract the ISO timestamp of the most recent digest, or None."""
    digests_dir = elmer_dir / "digests"
    if not digests_dir.exists():
        return None

    digest_files = sorted(digests_dir.glob("digest-*.md"), reverse=True)
    if not digest_files:
        return None

    # Extract timestamp from filename: digest-YYYY-MM-DDTHH-MM-SS.md
    ts_part = digest_files[0].stem.replace("digest-", "")
    parts = ts_part.split("T")
    if len(parts) == 2:
        date_part = parts[0]  # YYYY-MM-DD
        time_part = parts[1].replace("-", ":")  # HH:MM:SS
        return f"{date_part}T{time_part}"
    return ts_part


# --- Archive metadata parsing ---


def _parse_archive_metadata(path: Path) -> Optional[dict]:
    """Parse the HTML comment metadata header from an archived proposal.

    Returns a dict with keys: id, topic, archetype, model, status,
    decline_reason, merged_at, completed_at, archived. Returns None
    if the file has no parseable metadata header.
    """
    try:
        content = path.read_text()
    except Exception:
        return None

    match = re.match(r"<!--\s*elmer:archive\s*\n(.*?)-->", content, re.DOTALL)
    if not match:
        return None

    meta: dict = {"_content": content, "_path": path}
    for line in match.group(1).strip().splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta


def _load_archived_proposals(elmer_dir: Path) -> list[dict]:
    """Load all archived proposals with their metadata.

    Returns a list of metadata dicts, each including _content (full file)
    and _path. This is the archive's equivalent of state.list_explorations().
    """
    proposals_dir = elmer_dir / "proposals"
    if not proposals_dir.exists():
        return []

    results = []
    for path in sorted(proposals_dir.glob("*.md")):
        meta = _parse_archive_metadata(path)
        if meta:
            results.append(meta)
    return results


# --- Internal helpers ---


def _format_history(explorations: list, archived: list[dict]) -> str:
    """Format all explorations as a status list for the prompt.

    Merges in-flight DB records with archived completed records.
    Deduplicates by ID (DB takes precedence for active explorations).
    """
    seen_ids: set[str] = set()
    lines = []

    # DB records first (in-flight and recently completed)
    for exp in explorations:
        seen_ids.add(exp["id"])
        reason = ""
        try:
            if exp["status"] == "declined" and exp["decline_reason"]:
                reason = f" (reason: {exp['decline_reason']})"
        except (IndexError, KeyError):
            pass
        lines.append(f"- [{exp['status']}] {exp['topic']}{reason}")

    # Archived records (completed explorations that may have been cleaned from DB)
    for meta in archived:
        aid = meta.get("id", "")
        if aid in seen_ids:
            continue
        seen_ids.add(aid)
        status = meta.get("status", "unknown")
        topic = meta.get("topic", aid)
        reason = ""
        if status == "declined" and meta.get("decline_reason"):
            reason = f" (reason: {meta['decline_reason']})"
        lines.append(f"- [{status}] {topic}{reason}")

    return "\n".join(lines) if lines else ""


def _read_approved_proposals(
    elmer_dir: Path,
    explorations: list,
    archived: list[dict],
    *,
    since: Optional[str] = None,
    topic_filter: Optional[str] = None,
) -> str:
    """Read approved proposals from both DB records and archive.

    The archive is the source of truth for completed explorations (ADR-032).
    DB records are checked first; archive fills in anything cleaned from DB.
    """
    proposals_dir = elmer_dir / "proposals"
    seen_ids: set[str] = set()
    sections = []

    # From DB records (still in database)
    if proposals_dir.exists():
        for exp in explorations:
            if exp["status"] != "approved":
                continue
            if since and exp["merged_at"] and exp["merged_at"] < since:
                continue
            if topic_filter and topic_filter.lower() not in exp["topic"].lower():
                continue

            seen_ids.add(exp["id"])
            archive_path = proposals_dir / f"{exp['id']}.md"
            if archive_path.exists():
                content = archive_path.read_text()
                if len(content) > 3000:
                    content = content[:3000] + "\n\n[...truncated...]"
                sections.append(
                    f"### {exp['topic']} ({exp['archetype']})\n\n{content}"
                )

    # From archive (cleaned from DB but archive persists)
    for meta in archived:
        aid = meta.get("id", "")
        if aid in seen_ids:
            continue
        if meta.get("status") != "approved":
            continue
        if since and meta.get("merged_at") and meta["merged_at"] < since:
            continue
        topic = meta.get("topic", aid)
        if topic_filter and topic_filter.lower() not in topic.lower():
            continue

        seen_ids.add(aid)
        content = meta.get("_content", "")
        if len(content) > 3000:
            content = content[:3000] + "\n\n[...truncated...]"
        archetype = meta.get("archetype", "unknown")
        sections.append(f"### {topic} ({archetype})\n\n{content}")

    return "\n\n---\n\n".join(sections) if sections else ""


def _read_declined_proposals(
    explorations: list,
    archived: list[dict],
    *,
    since: Optional[str] = None,
    topic_filter: Optional[str] = None,
) -> str:
    """Format declined explorations with their reasons.

    Merges DB records with archive metadata for cleaned records.
    """
    seen_ids: set[str] = set()
    lines = []

    # From DB
    for exp in explorations:
        if exp["status"] != "declined":
            continue
        if since and exp.get("completed_at") and exp["completed_at"] < since:
            continue
        if topic_filter and topic_filter.lower() not in exp["topic"].lower():
            continue

        seen_ids.add(exp["id"])
        reason = ""
        try:
            reason = exp["decline_reason"] or ""
        except (IndexError, KeyError):
            pass

        if reason:
            lines.append(f"- **{exp['topic']}** — declined: {reason}")
        else:
            lines.append(f"- **{exp['topic']}** — declined (no reason recorded)")

    # From archive
    for meta in archived:
        aid = meta.get("id", "")
        if aid in seen_ids:
            continue
        if meta.get("status") != "declined":
            continue
        topic = meta.get("topic", aid)
        if since and meta.get("completed_at") and meta["completed_at"] < since:
            continue
        if topic_filter and topic_filter.lower() not in topic.lower():
            continue

        seen_ids.add(aid)
        reason = meta.get("decline_reason", "")
        if reason:
            lines.append(f"- **{topic}** — declined: {reason}")
        else:
            lines.append(f"- **{topic}** — declined (no reason recorded)")

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
