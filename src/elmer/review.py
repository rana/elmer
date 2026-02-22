"""Proposal review — read proposals, display status and summaries."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import click

from . import autoapprove, explore as explore_mod, state, worker, worktree as wt_mod


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


def _refresh_running(
    elmer_dir: Path,
    project_dir: Path = None,
    notify: Optional[Callable[[str], None]] = None,
) -> None:
    """Check running explorations and update status if finished.

    If project_dir is provided, also schedules pending explorations
    whose dependencies are now met.

    notify is a callback for status messages (default: click.echo).
    """
    if notify is None:
        notify = click.echo
    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn, status="running")

    newly_done = []
    for exp in explorations:
        pid = exp["pid"]
        if not worker.is_running(pid):
            worktree_path = Path(exp["worktree_path"])
            proposal_path = worktree_path / "PROPOSAL.md"

            # Extract cost data from the JSON log file (best-effort)
            cost_fields = {}
            log_path = elmer_dir / "logs" / f"{exp['id']}.log"
            cost_result = worker.parse_log_costs(log_path)
            if cost_result:
                cost_fields = {
                    k: v for k, v in {
                        "input_tokens": cost_result.input_tokens,
                        "output_tokens": cost_result.output_tokens,
                        "cost_usd": cost_result.cost_usd,
                        "num_turns_actual": cost_result.num_turns,
                    }.items() if v is not None
                }

            if proposal_path.exists():
                summary = _extract_summary(proposal_path)
                state.update_exploration(
                    conn,
                    exp["id"],
                    status="done",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    proposal_summary=summary,
                    **cost_fields,
                )
                newly_done.append(exp)
            else:
                state.update_exploration(
                    conn,
                    exp["id"],
                    status="failed",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    proposal_summary="(no PROPOSAL.md produced)",
                    **cost_fields,
                )
    conn.close()

    if project_dir:
        # Auto-approve flagged explorations that just finished
        for exp in newly_done:
            if exp["auto_approve"]:
                notify(f"Auto-reviewing: {exp['id']}...")
                approved = autoapprove.evaluate(elmer_dir, project_dir, exp["id"])
                if approved:
                    notify(f"  Auto-approved: {exp['id']}")
                else:
                    notify(f"  Queued for human review: {exp['id']}")

        # Schedule pending explorations whose dependencies are now met
        launched = explore_mod.schedule_ready(elmer_dir, project_dir)
        for slug in launched:
            notify(f"Unblocked and started: {slug}")


def show_status(elmer_dir: Path, project_dir: Path = None) -> None:
    """Display status of all explorations."""
    _refresh_running(elmer_dir, project_dir)

    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn)
    conn.close()

    if not explorations:
        click.echo("No explorations found. Run 'elmer explore \"topic\"' to start one.")
        return

    # Status indicators
    status_icons = {
        "pending": ".",
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
    click.echo(". pending  ~ running  * review ready  + approved  - rejected  ! failed")


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


def _score_proposal(exp, conn, project_dir: Path) -> tuple[float, list[str]]:
    """Score a proposal for prioritized review. Returns (score, reasons).

    Higher score = review first. Scoring factors:
    - Blockers: is anything waiting on this? (+30 per dependent)
    - Staleness: older proposals get priority (+1 per hour, max 24)
    - Diff size: smaller diffs are quicker to review (+10 if <50 lines)
    - Failed status: failed explorations need attention (+5)
    """
    score = 0.0
    reasons = []

    # Factor 1: Dependents — other explorations are blocked on this
    dependents = state.get_dependents(conn, exp["id"])
    if dependents:
        score += 30 * len(dependents)
        reasons.append(f"blocks {len(dependents)}")

    # Factor 2: Staleness — older proposals get priority
    try:
        created = datetime.fromisoformat(exp["created_at"])
        now = datetime.now(timezone.utc)
        hours = (now - created).total_seconds() / 3600
        staleness = min(hours, 24)
        score += staleness
        if hours > 12:
            reasons.append("stale")
    except (ValueError, TypeError):
        pass

    # Factor 3: Diff size — smaller = easier to review
    try:
        branch = exp["branch"]
        diff = wt_mod.get_branch_diff(project_dir, branch)
        # Count file lines in diff stat
        file_lines = [l for l in diff.strip().splitlines() if "|" in l]
        if len(file_lines) <= 5:
            score += 10
            reasons.append("small diff")
    except Exception:
        pass

    # Factor 4: Failed status — needs attention
    if exp["status"] == "failed":
        score += 5
        reasons.append("failed")

    return score, reasons


def list_proposals_prioritized(elmer_dir: Path, project_dir: Path) -> None:
    """List proposals ranked by review priority."""
    _refresh_running(elmer_dir, project_dir)

    conn = state.get_db(elmer_dir)
    done = state.list_explorations(conn, status="done")
    failed = state.list_explorations(conn, status="failed")
    proposals = list(done) + list(failed)

    if not proposals:
        click.echo("No proposals pending review.")
        conn.close()
        return

    # Score and sort
    scored = []
    for exp in proposals:
        score, reasons = _score_proposal(exp, conn, project_dir)
        scored.append((score, reasons, exp))

    conn.close()

    scored.sort(key=lambda x: -x[0])

    click.echo(f"{'#':<4} {'PRIORITY':>8} {'ID':<36} {'STATUS':<8} {'AGE':<8} {'REASONS'}")
    click.echo("-" * 100)

    for i, (score, reasons, exp) in enumerate(scored, 1):
        age = _age(exp["created_at"])
        reason_str = ", ".join(reasons) if reasons else "-"
        eid = exp["id"]
        if len(eid) > 34:
            eid = eid[:33] + ".."
        click.echo(
            f"{i:<4} {score:>8.0f} {eid:<36} {exp['status']:<8} {age:<8} {reason_str}"
        )

    click.echo(f"\n{len(scored)} proposal(s) ranked by review priority.")
    click.echo("Higher priority = review first.")
