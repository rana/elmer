"""Proposal review — read proposals, display status and summaries."""

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import click

from . import autoapprove, explore as explore_mod, state, synthesize as synth_mod, worker, worktree as wt_mod


def _is_ensemble_replica(exp) -> bool:
    """Check if an exploration is an ensemble replica (not synthesis, not standalone)."""
    try:
        return exp["ensemble_role"] == "replica"
    except (KeyError, IndexError):
        return False


def _term_width() -> int:
    """Get terminal width, defaulting to 82 for non-interactive contexts."""
    return shutil.get_terminal_size((82, 24)).columns


def _truncate(text: str, width: int) -> str:
    """Truncate text with '..' suffix if it exceeds width."""
    if len(text) > width:
        return text[: width - 2] + ".."
    return text


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


def _diagnose_failure(log_path: Path) -> str:
    """Extract a structured failure reason from a claude session log.

    Parses the JSON log to determine why PROPOSAL.md wasn't created,
    returning a human-readable reason string.
    """
    if not log_path.exists():
        return "(no log file — session may not have started)"

    try:
        raw = log_path.read_text().strip()
        if not raw:
            return "(empty log file — session produced no output)"
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return "(log file not valid JSON — session may have crashed)"

    # Handle streaming format (list of objects)
    if isinstance(data, list):
        for obj in reversed(data):
            if isinstance(obj, dict) and obj.get("type") == "result":
                data = obj
                break
        else:
            data = data[-1] if data else {}

    if not isinstance(data, dict):
        return "(unexpected log format)"

    # Check if claude reported an error
    if data.get("is_error"):
        result = str(data.get("result", ""))[:150]
        return f"(claude error: {result})"

    # Check if the result mentions PROPOSAL.md (wrote to wrong location)
    result = str(data.get("result", ""))
    if "PROPOSAL.md" in result or "proposal" in result.lower():
        # Check for explicit wrong-path writes
        import re
        paths = re.findall(r"written[^/]*(/[^\s\"']+PROPOSAL\.md)", result)
        if paths:
            return f"(PROPOSAL.md written to wrong path: {paths[0]})"
        return "(claude reported writing PROPOSAL.md but file not found in worktree)"

    # Check permission denials
    denials = data.get("permission_denials", [])
    if denials:
        tools = [d.get("tool_name", "?") for d in denials]
        return f"(no PROPOSAL.md; {len(denials)} permission denial(s): {', '.join(tools)})"

    num_turns = data.get("num_turns")
    return f"(no PROPOSAL.md produced — session completed {num_turns or '?'} turns normally)"


def parse_log_details(log_path: Path) -> Optional[dict]:
    """Parse a session log for display in `elmer logs`. Returns structured data or None."""
    if not log_path.exists():
        return None

    try:
        raw = log_path.read_text().strip()
        if not raw:
            return None
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return None

    # Handle streaming format
    if isinstance(data, list):
        for obj in reversed(data):
            if isinstance(obj, dict) and obj.get("type") == "result":
                data = obj
                break
        else:
            data = data[-1] if data else {}

    if not isinstance(data, dict):
        return None

    denials = data.get("permission_denials", [])

    return {
        "is_error": data.get("is_error", False),
        "num_turns": data.get("num_turns"),
        "duration_ms": data.get("duration_ms"),
        "cost_usd": data.get("total_cost_usd") or data.get("cost_usd"),
        "result_snippet": str(data.get("result", ""))[:500],
        "permission_denials": [
            {"tool": d.get("tool_name", "?"), "path": d.get("tool_input", {}).get("path", "")}
            for d in denials
        ],
        "model_usage": data.get("modelUsage", {}),
    }


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
                # Commit PROPOSAL.md to the branch so it survives worktree
                # removal and is recoverable via git show (ADR-034)
                wt_mod.commit_proposal_to_branch(worktree_path, exp["id"])

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
                reason = _diagnose_failure(log_path)
                state.update_exploration(
                    conn,
                    exp["id"],
                    status="failed",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    proposal_summary=reason,
                    **cost_fields,
                )

    # Check amending explorations — transition back to done when finished
    amending = state.list_explorations(conn, status="amending")
    for exp in amending:
        pid = exp["pid"]
        if not worker.is_running(pid):
            worktree_path = Path(exp["worktree_path"])
            proposal_path = worktree_path / "PROPOSAL.md"

            # Record amend cost (best-effort)
            log_path = elmer_dir / "logs" / f"{exp['id']}.log"
            cost_result = worker.parse_log_costs(log_path)
            if cost_result and cost_result.cost_usd is not None:
                state.record_meta_cost(
                    conn,
                    operation="amend",
                    model=exp["model"],
                    input_tokens=cost_result.input_tokens,
                    output_tokens=cost_result.output_tokens,
                    cost_usd=cost_result.cost_usd,
                    exploration_id=exp["id"],
                )

            # Update summary from revised proposal
            if proposal_path.exists():
                # Re-commit PROPOSAL.md after amendment (ADR-034)
                wt_mod.commit_proposal_to_branch(worktree_path, exp["id"])

                summary = _extract_summary(proposal_path)
                state.update_exploration(
                    conn, exp["id"],
                    status="done",
                    proposal_summary=summary,
                )
            else:
                state.update_exploration(conn, exp["id"], status="done")

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

        # Trigger ensemble synthesis for any ensembles where all replicas are done
        try:
            synthesized = synth_mod.trigger_ready_ensembles(
                elmer_dir, project_dir, notify=notify,
            )
        except Exception:
            pass  # Best-effort — never block the refresh


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
        "amending": "~",
        "done": "*",
        "approved": "+",
        "declined": "-",
        "failed": "!",
    }

    # Column layout — give ID all remaining space after fixed columns
    # Fixed: icon(2) + status(10) + archetype(14) + model(8) + age(6) + gaps(4) = 44
    tw = _term_width()
    id_w = max(20, tw - 44)
    total_w = id_w + 44

    # Header
    click.echo(f"{'ID':<{id_w}} {'STATUS':<10} {'ARCHETYPE':<14} {'MODEL':<8} {'AGE':<6}")
    click.echo("-" * total_w)

    # Group ensemble members for display
    seen_ensembles: set[str] = set()

    for exp in explorations:
        ens_id = exp["ensemble_id"] if "ensemble_id" in exp.keys() else None
        ens_role = exp["ensemble_role"] if "ensemble_role" in exp.keys() else None

        # Ensemble header — print once when we first encounter an ensemble
        if ens_id and ens_id not in seen_ensembles:
            seen_ensembles.add(ens_id)
            conn2 = state.get_db(elmer_dir)
            ens_status = state.get_ensemble_status(conn2, ens_id)
            replicas = state.get_ensemble_replicas(conn2, ens_id)
            conn2.close()
            click.echo(
                f"  {'ENSEMBLE: ' + ens_id:<{id_w - 2}} "
                f"{ens_status:<10} "
                f"{'':<14} {'':<8} "
                f"{len(replicas)} replica(s)"
            )

        icon = status_icons.get(exp["status"], " ")
        age = _age(exp["created_at"])

        if ens_role == "replica":
            # Indent replicas under their ensemble header
            eid = _truncate(exp["id"], id_w - 4)
            click.echo(
                f"  {icon} {eid:<{id_w - 4}} {exp['status']:<10} "
                f"{exp['archetype']:<14} {exp['model']:<8} {age:<6}"
            )
        elif ens_role == "synthesis":
            eid = _truncate(exp["id"], id_w - 4)
            click.echo(
                f"  {icon} {eid:<{id_w - 4}} {exp['status']:<10} "
                f"{'[synthesis]':<14} {exp['model']:<8} {age:<6}"
            )
        else:
            eid = _truncate(exp["id"], id_w - 2)
            click.echo(
                f"{icon} {eid:<{id_w - 2}} {exp['status']:<10} "
                f"{exp['archetype']:<14} {exp['model']:<8} {age:<6}"
            )

    # Legend
    click.echo()
    click.echo(". pending  ~ running/amending  * review ready  + approved  - declined  ! failed")


def list_proposals(elmer_dir: Path) -> None:
    """List explorations that have proposals ready for review.

    Ensemble replicas are hidden — only synthesis proposals are shown.
    """
    _refresh_running(elmer_dir)

    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn, status="done")
    conn.close()

    # Filter out ensemble replicas — only synthesis and standalone proposals
    reviewable = [
        exp for exp in explorations
        if not _is_ensemble_replica(exp)
    ]

    if not reviewable:
        click.echo("No proposals pending review.")
        return

    tw = _term_width()
    id_w = min(40, max(20, tw // 3))
    topic_w = max(20, tw - id_w - 2)

    click.echo(f"{'ID':<{id_w}} {'TOPIC':<{topic_w}}")
    click.echo("-" * tw)

    for exp in reviewable:
        eid = _truncate(exp["id"], id_w - 2)  # -2 for leading indent
        topic = _truncate(exp["topic"], topic_w)
        click.echo(f"  {eid:<{id_w - 2}} {topic}")

    click.echo(f"\n{len(reviewable)} proposal(s) ready for review.")
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


def show_log(elmer_dir: Path, exploration_id: str, *, raw: bool = False) -> None:
    """Display parsed session log for an exploration."""
    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)
    conn.close()

    if exp is None:
        click.echo(f"Exploration '{exploration_id}' not found.", err=True)
        sys.exit(1)

    log_path = elmer_dir / "logs" / f"{exp['id']}.log"

    if not log_path.exists():
        click.echo(f"No log file for '{exploration_id}'.")
        click.echo(f"Expected at: {log_path}")
        return

    if raw:
        click.echo(log_path.read_text())
        return

    details = parse_log_details(log_path)
    if details is None:
        click.echo("Log file exists but could not be parsed.")
        click.echo(f"File: {log_path}")
        return

    click.echo(f"Exploration: {exp['id']}")
    click.echo(f"Topic:       {exp['topic']}")
    click.echo(f"Status:      {exp['status']}")
    click.echo(f"Archetype:   {exp['archetype']}")
    click.echo(f"Model:       {exp['model']}")
    click.echo("-" * 60)

    is_err = details["is_error"]
    click.echo(f"Claude error:  {'YES' if is_err else 'no'}")
    click.echo(f"Turns:         {details['num_turns'] or '?'}")
    if details["duration_ms"]:
        mins = details["duration_ms"] / 60000
        click.echo(f"Duration:      {mins:.1f}m")
    if details["cost_usd"]:
        click.echo(f"Cost:          ${details['cost_usd']:.2f}")

    denials = details["permission_denials"]
    if denials:
        click.echo(f"\nPermission denials ({len(denials)}):")
        for d in denials:
            click.echo(f"  {d['tool']}: {d['path']}")

    models = details.get("model_usage", {})
    if models:
        click.echo("\nModel usage:")
        for model_id, usage in models.items():
            short = model_id.split(".")[-1].split("-v")[0] if "." in model_id else model_id
            cost = usage.get("costUSD", 0)
            inp = usage.get("inputTokens", 0) + usage.get("cacheReadInputTokens", 0)
            out = usage.get("outputTokens", 0)
            click.echo(f"  {short}: {inp:,} in / {out:,} out  ${cost:.2f}")

    snippet = details["result_snippet"]
    if snippet:
        click.echo(f"\nClaude's final response (first 500 chars):")
        click.echo("-" * 60)
        click.echo(snippet)

    click.echo(f"\nFull log: {log_path}")


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

    # Fixed: #(4) + priority(8) + status(8) + age(8) + gaps(3) + reasons(~20) = 51
    tw = _term_width()
    id_w = max(20, tw - 51)

    click.echo(f"{'#':<4} {'PRIORITY':>8} {'ID':<{id_w}} {'STATUS':<8} {'AGE':<8} {'REASONS'}")
    click.echo("-" * tw)

    for i, (score, reasons, exp) in enumerate(scored, 1):
        age = _age(exp["created_at"])
        reason_str = ", ".join(reasons) if reasons else "-"
        eid = _truncate(exp["id"], id_w)
        click.echo(
            f"{i:<4} {score:>8.0f} {eid:<{id_w}} {exp['status']:<8} {age:<8} {reason_str}"
        )

    click.echo(f"\n{len(scored)} proposal(s) ranked by review priority.")
    click.echo("Higher priority = review first.")
