"""Approval gate — approve (merge) or decline (discard) explorations."""

import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from . import config, explore as explore_mod, generate as gen_mod, insights, state, worker, worktree


def _archive_proposal(elmer_dir: Path, exp: dict, final_status: str) -> Optional[Path]:
    """Archive PROPOSAL.md before worktree cleanup. Returns archive path or None.

    Copies the proposal to .elmer/proposals/<id>.md with a metadata header.
    Best-effort: never blocks the approval/decline flow.
    """
    try:
        worktree_path = Path(exp["worktree_path"])
        proposal_path = worktree_path / "PROPOSAL.md"

        if not proposal_path.exists():
            return None

        archive_dir = elmer_dir / "proposals"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{exp['id']}.md"

        # Read original content
        content = proposal_path.read_text()

        # Prepend metadata as HTML comment (invisible in rendered markdown)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        meta = (
            f"<!-- elmer:archive\n"
            f"  id: {exp['id']}\n"
            f"  topic: {exp['topic']}\n"
            f"  archetype: {exp['archetype']}\n"
            f"  model: {exp['model']}\n"
            f"  status: {final_status}\n"
            f"  archived: {now}\n"
            f"-->\n\n"
        )

        archive_path.write_text(meta + content)
        return archive_path
    except Exception:
        return None  # Best-effort — never block the flow


def _cleanup_worktree(project_dir: Path, exp: dict) -> None:
    """Remove worktree and branch for an exploration."""
    worktree_path = Path(exp["worktree_path"])
    branch = exp["branch"]

    if worktree_path.exists():
        try:
            worktree.remove_worktree(project_dir, worktree_path)
        except subprocess.CalledProcessError:
            # Worktree may already be gone; force remove the directory
            import shutil
            shutil.rmtree(worktree_path, ignore_errors=True)
            # Prune worktree list
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=str(project_dir),
                capture_output=True,
            )

    try:
        worktree.delete_branch(project_dir, branch)
    except subprocess.CalledProcessError:
        pass  # Branch may already be gone


def _execute_chain_action(
    action: str,
    exploration_id: str,
    topic: str,
    project_dir: Path,
    notify=None,
) -> None:
    """Execute a chain action command with $ID and $TOPIC substitution."""
    if notify is None:
        notify = click.echo
    cmd = action.replace("$ID", exploration_id).replace("$TOPIC", topic)
    notify(f"Chain action: {cmd}")
    try:
        subprocess.run(
            shlex.split(cmd),
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        notify(f"Chain action failed: {e}")


def approve_exploration(
    elmer_dir: Path,
    project_dir: Path,
    exploration_id: str,
    *,
    auto_followup: bool = False,
    followup_count: int = 3,
    followup_model: Optional[str] = None,
    followup_auto_approve: bool = False,
    notify=None,
) -> None:
    """Approve an exploration: merge its branch and clean up.

    If auto_followup is True, generates follow-up topics and spawns
    them as new explorations after the merge.
    """
    if notify is None:
        notify = click.echo

    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)

    if exp is None:
        click.echo(f"Exploration '{exploration_id}' not found.", err=True)
        sys.exit(1)

    if exp["status"] not in ("done", "failed"):
        click.echo(
            f"Cannot approve exploration in status '{exp['status']}'. "
            f"Must be 'done' or 'failed'.",
            err=True,
        )
        sys.exit(1)

    # Merge branch
    branch = exp["branch"]
    try:
        worktree.merge_branch(
            project_dir,
            branch,
            f"Merge elmer exploration: {exp['topic']}",
        )
    except subprocess.CalledProcessError as e:
        click.echo(f"Merge failed (conflicts?):\n{e.stderr}", err=True)
        click.echo(
            f"Resolve manually, then run: elmer approve {exploration_id}",
            err=True,
        )
        sys.exit(1)

    # Remove PROPOSAL.md from main — it's an elmer artifact, not a project deliverable.
    # The proposal is archived to .elmer/proposals/ before worktree cleanup.
    try:
        worktree.remove_file_and_commit(
            project_dir,
            "PROPOSAL.md",
            f"Remove PROPOSAL.md (archived to .elmer/proposals/{exploration_id}.md)",
        )
    except subprocess.CalledProcessError:
        pass  # Best-effort: file may not exist on branch or may not be committed

    # Extract cross-project insights before cleanup (needs worktree for PROPOSAL.md)
    cfg = config.load_config(elmer_dir)
    ins_cfg = cfg.get("insights", {})
    if ins_cfg.get("enabled", False):
        try:
            extracted = insights.extract_insights(
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                exploration_id=exploration_id,
                model=ins_cfg.get("model", "sonnet"),
                max_turns=ins_cfg.get("max_turns", 3),
            )
            for ins in extracted:
                notify(f"Insight: {ins}")
        except Exception as e:
            notify(f"Insight extraction failed: {e}")

    # Archive proposal before cleanup
    _archive_proposal(elmer_dir, exp, "approved")

    # Cleanup
    _cleanup_worktree(project_dir, exp)

    state.update_exploration(
        conn,
        exploration_id,
        status="approved",
        merged_at=datetime.now(timezone.utc).isoformat(),
    )
    conn.close()

    # Schedule any pending explorations that were waiting on this one
    launched = explore_mod.schedule_ready(elmer_dir, project_dir)
    for slug in launched:
        notify(f"Unblocked and started: {slug}")

    # Execute on_approve chain action
    on_approve = exp["on_approve"] if "on_approve" in exp.keys() else None
    if on_approve:
        _execute_chain_action(
            on_approve, exploration_id, exp["topic"], project_dir, notify=notify,
        )

    # Generate follow-up topics
    if auto_followup:
        try:
            cfg = config.load_config(elmer_dir)
            fu_cfg = cfg.get("followup", {})
            fu_model = followup_model or fu_cfg.get("model", "sonnet")

            topics = gen_mod.generate_topics(
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                count=followup_count,
                follow_up_id=exploration_id,
                model=fu_model,
            )
            defaults = cfg.get("defaults", {})
            for topic in topics:
                slug, _ = explore_mod.start_exploration(
                    topic=topic,
                    archetype=exp["archetype"],
                    model=exp["model"],
                    max_turns=exp["max_turns"] or defaults.get("max_turns", 50),
                    elmer_dir=elmer_dir,
                    project_dir=project_dir,
                    parent_id=exploration_id,
                    auto_approve=followup_auto_approve,
                )
                notify(f"Follow-up started: {slug}")
        except RuntimeError as e:
            notify(f"Follow-up generation failed: {e}")


def decline_exploration(
    elmer_dir: Path, project_dir: Path, exploration_id: str, *, notify=None,
) -> None:
    """Decline an exploration: delete branch and clean up."""
    if notify is None:
        notify = click.echo

    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)

    if exp is None:
        click.echo(f"Exploration '{exploration_id}' not found.", err=True)
        sys.exit(1)

    if exp["status"] == "approved":
        click.echo("Cannot decline an already-approved exploration.", err=True)
        sys.exit(1)

    # Archive proposal before cleanup
    _archive_proposal(elmer_dir, exp, "declined")

    _cleanup_worktree(project_dir, exp)

    state.update_exploration(conn, exploration_id, status="declined")

    _warn_orphaned_dependents(conn, exploration_id, notify=notify)
    conn.close()

    # Execute on_decline chain action
    on_decline = exp["on_decline"] if "on_decline" in exp.keys() else None
    if on_decline:
        _execute_chain_action(
            on_decline, exploration_id, exp["topic"], project_dir, notify=notify,
        )


def _warn_orphaned_dependents(
    conn, exploration_id: str, notify=None,
) -> None:
    """Warn about pending explorations that depend on a declined/cancelled exploration."""
    if notify is None:
        notify = click.echo

    # Walk the dependency graph forward to find all transitive dependents
    orphaned = []
    queue = state.get_dependents(conn, exploration_id)
    visited = set()
    while queue:
        dep_id = queue.pop(0)
        if dep_id in visited:
            continue
        visited.add(dep_id)
        dep = state.get_exploration(conn, dep_id)
        if dep and dep["status"] == "pending":
            orphaned.append(dep_id)
            # This pending exploration's dependents are also affected
            queue.extend(state.get_dependents(conn, dep_id))

    if orphaned:
        notify(
            f"Warning: {len(orphaned)} pending exploration(s) depend on "
            f"'{exploration_id}' and can no longer start:"
        )
        for oid in orphaned:
            notify(f"  {oid}")
        notify("Use 'elmer decline ID' to discard them.")


def cancel_exploration(
    elmer_dir: Path, project_dir: Path, exploration_id: str, *, notify=None,
) -> None:
    """Cancel a running or pending exploration: stop the process, clean up."""
    if notify is None:
        notify = click.echo

    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)

    if exp is None:
        click.echo(f"Exploration '{exploration_id}' not found.", err=True)
        sys.exit(1)

    if exp["status"] not in ("running", "pending", "amending"):
        click.echo(
            f"Cannot cancel exploration in status '{exp['status']}'. "
            f"Must be 'running', 'pending', or 'amending'.",
            err=True,
        )
        sys.exit(1)

    # Stop the process if running or amending
    if exp["status"] in ("running", "amending") and exp["pid"]:
        stopped = worker.terminate(exp["pid"])
        if stopped:
            notify(f"Stopped process {exp['pid']}")
        else:
            notify(f"Process {exp['pid']} already stopped")

        # Extract cost data from log (best-effort)
        cost_fields = {}
        log_path = elmer_dir / "logs" / f"{exploration_id}.log"
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

        # Archive proposal before cleanup (may exist if cancelled mid-work)
        _archive_proposal(elmer_dir, exp, "cancelled")

        _cleanup_worktree(project_dir, exp)
        state.update_exploration(
            conn,
            exploration_id,
            status="declined",
            completed_at=datetime.now(timezone.utc).isoformat(),
            **cost_fields,
        )
    else:
        # Pending — no process or worktree to clean
        state.update_exploration(conn, exploration_id, status="declined")

    _warn_orphaned_dependents(conn, exploration_id, notify=notify)
    conn.close()

    # Execute on_decline chain action
    on_decline = exp["on_decline"] if "on_decline" in exp.keys() else None
    if on_decline:
        _execute_chain_action(
            on_decline, exploration_id, exp["topic"], project_dir, notify=notify,
        )


def approve_all(
    elmer_dir: Path,
    project_dir: Path,
    *,
    auto_followup: bool = False,
    followup_count: int = 3,
    followup_auto_approve: bool = False,
) -> list[str]:
    """Approve all explorations with status 'done'. Returns list of approved IDs."""
    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn, status="done")
    conn.close()

    approved = []
    for exp in explorations:
        try:
            approve_exploration(
                elmer_dir, project_dir, exp["id"],
                auto_followup=auto_followup,
                followup_count=followup_count,
                followup_auto_approve=followup_auto_approve,
            )
            approved.append(exp["id"])
        except SystemExit:
            # Abort the failed merge so subsequent approvals aren't poisoned
            worktree.abort_merge(project_dir)
            click.echo(f"Skipping {exp['id']} (merge failed)")
    return approved


def retry_exploration(
    elmer_dir: Path, project_dir: Path, exploration_id: str, *, notify=None,
) -> str:
    """Retry a failed exploration: clean up old state and re-spawn with same parameters.

    Returns the new exploration slug.
    """
    if notify is None:
        notify = click.echo

    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)

    if exp is None:
        click.echo(f"Exploration '{exploration_id}' not found.", err=True)
        sys.exit(1)

    if exp["status"] != "failed":
        click.echo(
            f"Cannot retry exploration in status '{exp['status']}'. "
            f"Must be 'failed'.",
            err=True,
        )
        sys.exit(1)

    # Extract parameters from the failed exploration
    topic = exp["topic"]
    archetype = exp["archetype"]
    model = exp["model"]
    max_turns = exp["max_turns"] or 50
    auto_approve = bool(exp["auto_approve"])
    generate_prompt = bool(exp["generate_prompt"])
    budget_usd = exp["budget_usd"]

    # Archive proposal before cleanup (failed explorations may still have partial output)
    _archive_proposal(elmer_dir, exp, "retried")

    # Clean up the failed exploration's worktree and branch
    _cleanup_worktree(project_dir, exp)
    state.delete_exploration(conn, exploration_id)
    conn.close()

    # Re-spawn with the same parameters
    slug, _ = explore_mod.start_exploration(
        topic=topic,
        archetype=archetype,
        model=model,
        max_turns=max_turns,
        elmer_dir=elmer_dir,
        project_dir=project_dir,
        auto_approve=auto_approve,
        generate_prompt=generate_prompt,
        budget_usd=budget_usd,
    )
    return slug


def retry_all_failed(
    elmer_dir: Path, project_dir: Path, *, max_concurrent: Optional[int] = None, notify=None,
) -> list[str]:
    """Retry all failed explorations. Returns list of new slugs.

    If max_concurrent is set, only the first N retry immediately;
    the rest are queued with sliding-window dependencies.
    """
    if notify is None:
        notify = click.echo

    conn = state.get_db(elmer_dir)
    failed = state.list_explorations(conn, status="failed")
    conn.close()

    if not failed:
        notify("No failed explorations to retry.")
        return []

    retried: list[str] = []
    for i, exp in enumerate(failed):
        try:
            conn = state.get_db(elmer_dir)
            # Re-read to ensure it's still failed (may have been cleaned between iterations)
            current = state.get_exploration(conn, exp["id"])
            conn.close()
            if current is None or current["status"] != "failed":
                continue

            # Determine dependencies for concurrency throttle
            dep_list = None
            if max_concurrent is not None and i >= max_concurrent:
                dep_list = [retried[i - max_concurrent]]

            topic = exp["topic"]
            archetype = exp["archetype"]
            model = exp["model"]
            max_turns = exp["max_turns"] or 50
            auto_approve = bool(exp["auto_approve"])
            generate_prompt = bool(exp["generate_prompt"])
            budget_usd = exp["budget_usd"]

            # Archive and clean up old state
            _archive_proposal(elmer_dir, exp, "retried")
            _cleanup_worktree(project_dir, exp)
            conn = state.get_db(elmer_dir)
            state.delete_exploration(conn, exp["id"])
            conn.close()

            slug, _ = explore_mod.start_exploration(
                topic=topic,
                archetype=archetype,
                model=model,
                max_turns=max_turns,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                depends_on=dep_list,
                auto_approve=auto_approve,
                generate_prompt=generate_prompt,
                budget_usd=budget_usd,
            )
            retried.append(slug)
            if dep_list:
                notify(f"Queued:   {slug} (waiting for {dep_list[0]})")
            else:
                notify(f"Retrying: {slug}")
        except (RuntimeError, FileNotFoundError) as e:
            notify(f"Error retrying {exp['id']}: {e}")

    return retried


def clean_all(elmer_dir: Path, project_dir: Path) -> int:
    """Clean up worktrees for completed explorations. Returns count cleaned."""
    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn)

    cleaned = 0
    for exp in explorations:
        if exp["status"] in ("approved", "declined", "failed"):
            # Archive proposal before cleanup
            _archive_proposal(elmer_dir, exp, exp["status"])

            worktree_path = Path(exp["worktree_path"])
            if worktree_path.exists():
                _cleanup_worktree(project_dir, exp)
                cleaned += 1
            state.delete_exploration(conn, exp["id"])
            cleaned += 1

    conn.close()

    # Prune any orphaned worktrees
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=str(project_dir),
        capture_output=True,
    )

    return cleaned
