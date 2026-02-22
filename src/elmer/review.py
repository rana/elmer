"""Proposal review — read proposals, display status and summaries."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from . import state, worker


def _age(iso_timestamp: str) -> str:
    """Format an ISO timestamp as a human-readable age."""
    try:
        created = datetime.fromisoformat(iso_timestamp)
        now = datetime.now(timezone.utc)
        delta = now - created
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h {minutes % 60}m"
        days = hours // 24
        return f"{days}d {hours % 24}h"
    except (ValueError, TypeError):
        return "?"


def _extract_summary(proposal_path: Path, max_lines: int = 5) -> str:
    """Extract the first few meaningful lines from a proposal."""
    if not proposal_path.exists():
        return "(no proposal)"
    lines = proposal_path.read_text().splitlines()
    summary_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            summary_lines.append(stripped)
        elif stripped.startswith("## Summary"):
            continue  # skip the heading, grab content below
        if len(summary_lines) >= max_lines:
            break
    return " ".join(summary_lines)[:200] if summary_lines else "(empty proposal)"


def _refresh_running(elmer_dir: Path) -> None:
    """Check running explorations and update status if finished."""
    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn, status="running")

    for exp in explorations:
        pid = exp["pid"]
        if not worker.is_running(pid):
            worktree_path = Path(exp["worktree_path"])
            proposal_path = worktree_path / "PROPOSAL.md"

            if proposal_path.exists():
                summary = _extract_summary(proposal_path)
                state.update_exploration(
                    conn,
                    exp["id"],
                    status="done",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    proposal_summary=summary,
                )
            else:
                state.update_exploration(
                    conn,
                    exp["id"],
                    status="failed",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    proposal_summary="(no PROPOSAL.md produced)",
                )
    conn.close()


def show_status(elmer_dir: Path) -> None:
    """Display status of all explorations."""
    _refresh_running(elmer_dir)

    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn)
    conn.close()

    if not explorations:
        click.echo("No explorations found. Run 'elmer explore \"topic\"' to start one.")
        return

    # Status indicators
    status_icons = {
        "running": "~",
        "done": "*",
        "approved": "+",
        "rejected": "-",
        "failed": "!",
    }

    # Header
    click.echo(
        f"{'ID':<40} {'STATUS':<10} {'ARCHETYPE':<14} {'MODEL':<8} {'AGE':<10}"
    )
    click.echo("-" * 82)

    for exp in explorations:
        icon = status_icons.get(exp["status"], " ")
        age = _age(exp["created_at"])
        click.echo(
            f"{icon} {exp['id']:<38} {exp['status']:<10} "
            f"{exp['archetype']:<14} {exp['model']:<8} {age:<10}"
        )

    # Legend
    click.echo()
    click.echo("~ running  * review ready  + approved  - rejected  ! failed")


def list_proposals(elmer_dir: Path) -> None:
    """List explorations that have proposals ready for review."""
    _refresh_running(elmer_dir)

    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn, status="done")
    conn.close()

    if not explorations:
        click.echo("No proposals pending review.")
        return

    click.echo(f"{'ID':<40} {'TOPIC':<60}")
    click.echo("-" * 100)

    for exp in explorations:
        topic = exp["topic"][:58] + ".." if len(exp["topic"]) > 60 else exp["topic"]
        click.echo(f"  {exp['id']:<38} {topic}")

    click.echo(f"\n{len(explorations)} proposal(s) ready for review.")
    click.echo("Use 'elmer review <id>' to read a proposal.")


def show_proposal(elmer_dir: Path, exploration_id: str) -> None:
    """Display a full proposal."""
    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)
    conn.close()

    if exp is None:
        click.echo(f"Exploration '{exploration_id}' not found.", err=True)
        sys.exit(1)

    worktree_path = Path(exp["worktree_path"])
    proposal_path = worktree_path / "PROPOSAL.md"

    click.echo(f"Exploration: {exp['id']}")
    click.echo(f"Topic:       {exp['topic']}")
    click.echo(f"Status:      {exp['status']}")
    click.echo(f"Archetype:   {exp['archetype']}")
    click.echo(f"Model:       {exp['model']}")
    click.echo(f"Branch:      {exp['branch']}")
    click.echo(f"Created:     {exp['created_at']}")
    if exp["completed_at"]:
        click.echo(f"Completed:   {exp['completed_at']}")
    click.echo("-" * 60)

    if proposal_path.exists():
        click.echo(proposal_path.read_text())
    else:
        click.echo("(No PROPOSAL.md found)")
        log_path = elmer_dir / "logs" / f"{exp['id']}.log"
        if log_path.exists():
            click.echo(f"\nLog available at: {log_path}")
