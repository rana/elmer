"""Plan lifecycle — status tracking, resume, completion verification.

Manages the lifecycle of implementation plans after creation: querying
status, displaying progress, resuming paused plans, and running
integration verification checks.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from . import config, invariants, state


def get_plan_status(elmer_dir: Path, plan_id: Optional[str] = None) -> list[dict]:
    """Get status of active plans with per-step progress."""
    conn = state.get_db(elmer_dir)

    if plan_id:
        plans = [state.get_plan(conn, plan_id)]
        plans = [p for p in plans if p is not None]
    else:
        plans = state.list_plans(conn)

    results = []
    for plan in plans:
        plan_dict = dict(plan)
        exps = state.get_plan_explorations(conn, plan["id"])

        steps_status = []
        total_cost = 0.0
        for exp in exps:
            step_info = {
                "step": exp["plan_step"],
                "id": exp["id"],
                "status": exp["status"],
                "archetype": exp["archetype"],
                "cost_usd": exp["cost_usd"],
                "verify_cmd": exp["verify_cmd"],
                "amend_count": exp["amend_count"] or 0,
                "verification_failures": exp["verification_failures"] or 0,
                "verification_seconds": exp["verification_seconds"] or 0.0,
            }
            if exp["cost_usd"] is not None:
                total_cost += exp["cost_usd"]
            steps_status.append(step_info)

        plan_dict["steps"] = steps_status
        plan_dict["total_cost"] = total_cost

        # Derive plan status from step statuses
        statuses = [s["status"] for s in steps_status]
        if all(s == "approved" for s in statuses):
            if plan_dict["status"] != "completed":
                state.update_plan(
                    conn, plan["id"],
                    status="completed",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    total_cost_usd=total_cost,
                )
                plan_dict["status"] = "completed"
                plan_dict["_newly_completed"] = True
        elif any(s == "failed" for s in statuses):
            if plan_dict["status"] == "active":
                state.update_plan(conn, plan["id"], status="paused")
                plan_dict["status"] = "paused"

        results.append(plan_dict)

    conn.close()
    return results


def show_plan_status(elmer_dir: Path, plan_id: Optional[str] = None) -> None:
    """Display plan status to the terminal."""
    plans = get_plan_status(elmer_dir, plan_id)

    if not plans:
        if plan_id:
            click.echo(f"Plan '{plan_id}' not found.")
        else:
            click.echo("No implementation plans found.")
        return

    status_icons = {
        "pending": ".",
        "running": "~",
        "amending": "~",
        "done": "*",
        "approved": "+",
        "declined": "-",
        "failed": "!",
    }

    for plan in plans:
        click.echo(f"Plan: {plan['id']}")
        click.echo(f"  Milestone: {plan['milestone_ref']}")
        click.echo(f"  Status:    {plan['status']}")
        if plan.get("total_cost") is not None:
            click.echo(f"  Cost:      ${plan['total_cost']:.2f}")
        revision_count = plan.get("revision_count") or 0
        if revision_count > 0:
            trigger = plan.get("replan_trigger_step")
            trigger_note = f" (triggered by step {trigger})" if trigger is not None else ""
            click.echo(f"  Revisions: {revision_count}{trigger_note}")
        click.echo()

        steps = plan.get("steps", [])
        if not steps:
            click.echo("  (no steps)")
            continue

        # Parse original plan for titles and duration estimates
        try:
            original = json.loads(plan["plan_json"])
            titles = {i: s.get("title", "") for i, s in enumerate(original.get("steps", []))}
            step_estimates = {i: s.get("estimated_seconds") for i, s in enumerate(original.get("steps", []))}
        except (json.JSONDecodeError, KeyError):
            titles = {}
            step_estimates = {}

        for step in steps:
            icon = status_icons.get(step["status"], " ")
            title = titles.get(step["step"], step["id"])
            amend_info = f" (amended {step['amend_count']}x)" if step["amend_count"] else ""
            vfail_info = f" ({step['verification_failures']} verify fail)" if step.get("verification_failures") else ""
            cost_info = f" ${step['cost_usd']:.2f}" if step.get("cost_usd") else ""
            click.echo(f"  {icon} Step {step['step']}: {title}  [{step['status']}{amend_info}{vfail_info}{cost_info}]")

        # Summary
        approved = sum(1 for s in steps if s["status"] == "approved")
        total_vfails = sum(s.get("verification_failures", 0) for s in steps)
        vfail_note = f", {total_vfails} verification failure(s)" if total_vfails else ""

        # Duration estimates from plan JSON
        estimates = [v for v in step_estimates.values() if isinstance(v, (int, float)) and v >= 0]
        est_note = ""
        if estimates:
            est_hours = sum(estimates) / 3600
            est_note = f", est. {est_hours:.1f}h"

        # Actual verification time
        total_vsecs = sum(s.get("verification_seconds", 0) for s in steps)
        vsecs_note = f", {total_vsecs:.0f}s verify time" if total_vsecs > 0 else ""

        click.echo(f"\n  Progress: {approved}/{len(steps)} steps approved{vfail_note}{est_note}{vsecs_note}")
        click.echo()


def resume_plan(
    *,
    plan_id: str,
    elmer_dir: Path,
    project_dir: Path,
) -> None:
    """Resume a paused plan by retrying the failed step."""
    conn = state.get_db(elmer_dir)
    plan = state.get_plan(conn, plan_id)

    if plan is None:
        conn.close()
        raise RuntimeError(f"Plan '{plan_id}' not found")

    if plan["status"] not in ("paused", "active"):
        conn.close()
        raise RuntimeError(f"Plan '{plan_id}' is {plan['status']}, not resumable")

    # Find failed explorations in this plan
    exps = state.get_plan_explorations(conn, plan_id)
    failed = [e for e in exps if e["status"] == "failed"]

    if not failed:
        # No failures — just un-pause and let daemon schedule pending
        state.update_plan(conn, plan_id, status="active")
        conn.close()
        click.echo(f"Plan '{plan_id}' resumed. No failed steps — pending steps will be scheduled.")
        return

    # Separate root-cause failures from cascade failures (ADR-049).
    root_failures = [
        e for e in failed
        if not (e.get("proposal_summary") or "").startswith("(dependency failed:")
    ]
    cascade_failures = [
        e for e in failed
        if (e.get("proposal_summary") or "").startswith("(dependency failed:")
    ]

    # Reset amend counts and retry root-cause failed explorations
    state.update_plan(conn, plan_id, status="active")
    conn.close()

    from . import gate  # late import to avoid circular
    retried = 0
    for exp in root_failures:
        click.echo(f"Retrying: {exp['id']}")
        try:
            gate.retry_exploration(
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                exploration_id=exp["id"],
            )
            retried += 1
        except RuntimeError as e:
            click.echo(f"  Retry failed: {e}", err=True)

    if cascade_failures and not root_failures:
        # All failures are cascade-only — rebuild deps to reset them to pending
        gate._rebuild_plan_dependencies(elmer_dir, plan_id, notify=click.echo)

    click.echo(
        f"Plan '{plan_id}' resumed. {retried} step(s) retried"
        + (f", {len(cascade_failures)} cascade-failed step(s) reset to pending" if cascade_failures else "")
        + "."
    )


def get_completion_verify_cmd(
    elmer_dir: Path,
    plan_id: str,
) -> tuple[str | None, str | None]:
    """Resolve the completion verification command for a plan.

    Returns (verify_cmd, source) where source describes where the command
    came from (for logging), or (None, None) if no command is configured.

    Priority order:
    1. completion_verify_cmd in plan JSON
    2. global [verification] on_done from config
    3. last step's verify_cmd
    """
    conn = state.get_db(elmer_dir)
    plan = state.get_plan(conn, plan_id)
    if plan is None:
        conn.close()
        return None, None

    verify_cmd = None
    source = None

    # Priority 1: completion_verify_cmd in plan JSON
    try:
        plan_json = json.loads(plan["plan_json"])
        verify_cmd = plan_json.get("completion_verify_cmd")
        if verify_cmd:
            source = "plan completion_verify_cmd"
    except (json.JSONDecodeError, KeyError):
        plan_json = {}

    # Priority 2: global [verification] on_done from config
    if not verify_cmd:
        cfg = config.load_config(elmer_dir)
        verify_cmd = cfg.get("verification", {}).get("on_done")
        if verify_cmd:
            source = "config [verification] on_done"

    # Priority 3: last step's verify_cmd
    if not verify_cmd:
        steps = plan_json.get("steps", [])
        if steps:
            verify_cmd = steps[-1].get("verify_cmd")
            if verify_cmd:
                source = "last step verify_cmd"

    conn.close()
    return verify_cmd, source


def is_last_plan_step(
    elmer_dir: Path,
    plan_id: str,
    exploration_id: str,
) -> bool:
    """Check if approving this exploration would complete the plan.

    Returns True if all OTHER steps in the plan are already approved
    and this is the only non-approved step remaining.
    """
    conn = state.get_db(elmer_dir)
    plan_exps = state.get_plan_explorations(conn, plan_id)
    conn.close()

    if not plan_exps:
        return False

    non_approved = [e for e in plan_exps if e["status"] != "approved"]
    return len(non_approved) == 1 and non_approved[0]["id"] == exploration_id


def run_completion_check(
    elmer_dir: Path,
    project_dir: Path,
    plan_id: str,
    *,
    cwd: Path | None = None,
    notify=None,
) -> bool:
    """Run integration verification for a plan.

    Checks that the assembled project works as a whole. Uses the plan's
    completion_verify_cmd, the global [verification] on_done, or the last
    step's verify_cmd as fallback.

    If cwd is provided, runs the command there (e.g., in the last step's
    worktree for pre-approval checks). Otherwise runs in project_dir.

    Returns True if verification passed (or no command to run).
    """
    if notify is None:
        notify = click.echo

    verify_cmd, source = get_completion_verify_cmd(elmer_dir, plan_id)

    conn = state.get_db(elmer_dir)
    plan = state.get_plan(conn, plan_id)
    if plan is None:
        conn.close()
        return True

    if not verify_cmd:
        # Auto-detect doc-only projects and use coherence verification (ADR-056)
        if invariants.is_doc_only_project(project_dir):
            conn.close()
            return _run_coherence_completion_check(
                elmer_dir, project_dir, plan_id, notify=notify,
            )
        conn.close()
        notify(f"  Plan {plan_id}: no completion verification command configured")
        return True

    run_dir = cwd or project_dir
    location = "worktree" if cwd else "project"
    notify(f"  Plan {plan_id}: running integration verification ({location})...")
    notify(f"    Command: {verify_cmd}")

    try:
        result = subprocess.run(
            verify_cmd,
            shell=True,
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            timeout=600,
        )
        output = (result.stdout + result.stderr).strip()
        if len(output) > 2000:
            output = output[:2000] + "\n... (truncated)"

        if result.returncode == 0:
            notify(f"  Plan {plan_id}: integration verification PASSED")
            state.update_plan(
                conn, plan_id,
                completion_note=f"Integration verification passed: {verify_cmd}",
            )
            conn.close()
            return True
        else:
            notify(f"  Plan {plan_id}: integration verification FAILED (exit {result.returncode})")
            notify(f"    {output[:500]}")
            state.update_plan(
                conn, plan_id,
                status="paused",
                completion_note=f"Integration verification failed (exit {result.returncode}): {output[:500]}",
            )
            conn.close()
            return False
    except subprocess.TimeoutExpired:
        notify(f"  Plan {plan_id}: integration verification timed out (600s)")
        state.update_plan(
            conn, plan_id,
            completion_note="Integration verification timed out",
        )
        conn.close()
        return False
    except (FileNotFoundError, OSError) as e:
        notify(f"  Plan {plan_id}: integration verification error: {e}")
        conn.close()
        return False


def _run_coherence_completion_check(
    elmer_dir: Path,
    project_dir: Path,
    plan_id: str,
    *,
    notify=None,
) -> bool:
    """Run document-coherence verification as a plan completion check.

    Auto-triggered for doc-only projects when no explicit verify_cmd is
    configured (ADR-056). Validates project invariants in check-only mode
    (no fixes) and returns True if all pass.
    """
    if notify is None:
        notify = click.echo

    notify(f"  Plan {plan_id}: doc-only project detected — running coherence verification...")

    conn = state.get_db(elmer_dir)
    plan = state.get_plan(conn, plan_id)

    try:
        passed, detail = invariants.run_coherence_check(
            elmer_dir=elmer_dir,
            project_dir=project_dir,
        )
    except RuntimeError as e:
        notify(f"  Plan {plan_id}: coherence verification error: {e}")
        conn.close()
        return False

    if passed:
        notify(f"  Plan {plan_id}: coherence verification PASSED")
        if plan:
            state.update_plan(
                conn, plan_id,
                completion_note="Document coherence verification passed (auto-detected doc-only project)",
            )
    else:
        notify(f"  Plan {plan_id}: coherence verification FAILED")
        notify(f"    {detail[:500]}")
        if plan:
            state.update_plan(
                conn, plan_id,
                status="paused",
                completion_note=f"Document coherence verification failed:\n{detail[:500]}",
            )

    conn.close()
    return passed
