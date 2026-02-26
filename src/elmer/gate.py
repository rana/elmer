"""Approval gate — approve (merge) or decline (discard) explorations."""

import json
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from . import config, explore as explore_mod, generate as gen_mod, insights, review, state, synthesize as synth_mod, worker, worktree


def _archive_has_id(path: Path, exploration_id: str) -> bool:
    """Check if an archived proposal contains the given exploration ID in metadata."""
    try:
        with open(path) as f:
            head = f.read(500)
        return f"\n  id: {exploration_id}\n" in head
    except (OSError, UnicodeDecodeError):
        return False


def _resolve_archive_path(archive_dir: Path, exp: dict) -> tuple[Path, bool]:
    """Resolve the archive path for a proposal (ADR-036: topic-derived filenames).

    Returns (path, already_archived). Uses the exploration topic to generate
    a human-readable filename instead of the exploration ID.
    """
    ens_role = exp.get("ensemble_role")
    if ens_role == "synthesis" and exp.get("ensemble_id"):
        # Use ensemble_id (already a bounded slug) for synthesis archives
        slug = f"{exp['ensemble_id']}-synthesis"
    else:
        topic = exp['topic']
        # Strip [synthesis] prefix added by synthesize_ensemble()
        clean_topic = re.sub(r'^\[synthesis\]\s*', '', topic)
        slug = explore_mod.slugify(clean_topic, max_length=60)
        if not slug:
            slug = "exploration"

    base_path = archive_dir / f"{slug}.md"

    # Idempotency: if file exists with same ID, it's a crash-recovery re-archive
    if base_path.exists():
        if _archive_has_id(base_path, exp['id']):
            return base_path, True
        # Collision with different exploration — add counter
        counter = 2
        while True:
            candidate = archive_dir / f"{slug}-{counter}.md"
            if not candidate.exists():
                return candidate, False
            if _archive_has_id(candidate, exp['id']):
                return candidate, True
            counter += 1

    return base_path, False


def _archive_proposal(
    elmer_dir: Path, exp: dict, final_status: str, *,
    project_dir: Optional[Path] = None,
    decline_reason: Optional[str] = None,
    notify=None,
) -> Optional[Path]:
    """Archive PROPOSAL.md before worktree cleanup. Returns archive path or None.

    Copies the proposal to .elmer/proposals/ with a topic-derived filename
    and a metadata header (ADR-036). If decline_reason is provided, it is
    included in the archive metadata.

    Recovery strategies (ADR-033):
    1. Return existing archive if present (idempotency for crash recovery)
    2. Read from worktree (normal path)
    3. Read from git branch via 'git show' (fallback when worktree is gone)

    Calls notify with warnings when using fallback strategies or when archival
    fails entirely. Returns None only when all strategies are exhausted.
    """
    if notify is None:
        notify = lambda msg: None  # Silent for backward compat

    # Normalize sqlite3.Row to dict so .get() works throughout
    if not isinstance(exp, dict):
        exp = dict(exp)

    archive_dir = elmer_dir / "proposals"

    # Resolve filename and check idempotency (ADR-036: topic-derived filenames)
    archive_path, already_exists = _resolve_archive_path(archive_dir, exp)
    if already_exists:
        return archive_path

    try:
        content = None
        recovered_from = None

        # Strategy 1: Read from worktree (normal path)
        worktree_path = Path(exp["worktree_path"])
        proposal_path = worktree_path / "PROPOSAL.md"
        if proposal_path.exists():
            content = proposal_path.read_text()

        # Strategy 2: Read from git branch (when worktree is gone)
        if content is None and project_dir is not None:
            branch = exp.get("branch", "")
            if branch:
                content = worktree.read_file_from_branch(
                    project_dir, branch, "PROPOSAL.md",
                )
                if content is not None:
                    recovered_from = "git branch"
                    notify(f"  Recovered proposal from git branch: {exp['id']}")

        if content is None:
            notify(
                f"  WARNING: No PROPOSAL.md found for {exp['id']} "
                f"(worktree gone, branch unavailable)"
            )
            return None

        # Write archive
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Prepend metadata as HTML comment (invisible in rendered markdown)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        reason_line = f"  decline_reason: {decline_reason}\n" if decline_reason else ""
        merged_line = f"  merged_at: {exp['merged_at']}\n" if exp.get("merged_at") else ""
        completed_line = f"  completed_at: {exp['completed_at']}\n" if exp.get("completed_at") else ""
        # Ensemble membership — preserved so digests and slug checks work after DB cleanup
        ens_id = exp.get("ensemble_id")
        ens_role = exp.get("ensemble_role")
        ensemble_line = f"  ensemble_id: {ens_id}\n" if ens_id else ""
        role_line = f"  ensemble_role: {ens_role}\n" if ens_role else ""
        recovery_line = f"  recovered_from: {recovered_from}\n" if recovered_from else ""
        meta = (
            f"<!-- elmer:archive\n"
            f"  id: {exp['id']}\n"
            f"  topic: {exp['topic']}\n"
            f"  archetype: {exp['archetype']}\n"
            f"  model: {exp['model']}\n"
            f"  status: {final_status}\n"
            f"{reason_line}"
            f"{merged_line}"
            f"{completed_line}"
            f"{ensemble_line}"
            f"{role_line}"
            f"{recovery_line}"
            f"  archived: {now}\n"
            f"-->\n\n"
        )

        archive_path.write_text(meta + content)
        return archive_path
    except Exception as e:
        notify(f"  WARNING: Archive failed for {exp['id']}: {e}")
        return None


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
    no_clean: bool = False,
    notify=None,
) -> None:
    """Approve an exploration: merge its branch and clean up.

    By default, deletes the DB record after approval (ADR-032). The
    archive at .elmer/proposals/ is the permanent record. Use no_clean=True
    to keep the DB record for inspection.

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

    # Merge branch (skip if already merged — crash recovery)
    branch = exp["branch"]
    already_merged = worktree.branch_exists(project_dir, branch) and worktree.is_ancestor(project_dir, branch)
    if already_merged:
        notify(f"Branch already merged, skipping merge step (crash recovery)")
    else:
        try:
            worktree.merge_branch(
                project_dir,
                branch,
                f"Merge elmer exploration: {exp['topic']}",
            )
        except subprocess.CalledProcessError as e:
            # Merge conflict: for plan steps, attempt auto-resolution (ADR-046).
            # Plan steps' changes are authoritative — they were verified individually.
            # Use -X theirs to prefer the branch's version on conflicts.
            is_plan_step = bool(exp["plan_id"] if "plan_id" in exp.keys() else None)
            worktree.abort_merge(project_dir)

            if is_plan_step:
                notify(f"Merge conflict for plan step {exploration_id}, retrying with -X theirs...")
                try:
                    worktree.merge_branch(
                        project_dir,
                        branch,
                        f"Merge elmer exploration: {exp['topic']}",
                        strategy_option="theirs",
                    )
                    notify(f"  Auto-resolved merge conflict for {exploration_id}")
                except subprocess.CalledProcessError:
                    worktree.abort_merge(project_dir)
                    click.echo(f"Merge failed even with -X theirs:\n{e.stderr}", err=True)
                    click.echo(
                        f"Resolve manually, then run: elmer approve {exploration_id}",
                        err=True,
                    )
                    sys.exit(1)
            else:
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
            f"Remove PROPOSAL.md (archived to .elmer/proposals/)",
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

    # Archive proposal before cleanup (ADR-033: archive-before-destroy)
    archive_path = _archive_proposal(
        elmer_dir, exp, "approved",
        project_dir=project_dir, notify=notify,
    )
    if archive_path is None and Path(exp["worktree_path"]).exists():
        # Archive failed but worktree still has data — preserve it
        notify(
            f"WARNING: Could not archive proposal for {exploration_id}. "
            f"Worktree preserved at {exp['worktree_path']}."
        )
        state.update_exploration(
            conn, exploration_id,
            status="approved",
            merged_at=datetime.now(timezone.utc).isoformat(),
        )
        conn.close()
        return

    # Cleanup
    _cleanup_worktree(project_dir, exp)

    state.update_exploration(
        conn,
        exploration_id,
        status="approved",
        merged_at=datetime.now(timezone.utc).isoformat(),
    )

    # Ensemble cascade: when approving a synthesis, cleanup all replicas.
    # Replica proposals are NOT archived — the synthesis is the permanent record
    # and embeds all replica content (ADR-036). Sleep between worktree removals
    # (including the first, since synthesis worktree was just removed above)
    # to prevent IDE inotify storms.
    ens_role = exp["ensemble_role"] if "ensemble_role" in exp.keys() else None
    ens_id = exp["ensemble_id"] if "ensemble_id" in exp.keys() else None
    if ens_role == "synthesis" and ens_id:
        replicas = state.get_ensemble_replicas(conn, ens_id)
        for replica in replicas:
            if replica["status"] not in ("approved", "declined"):
                time.sleep(1.0)
                _cleanup_worktree(project_dir, replica)
                state.update_exploration(
                    conn, replica["id"],
                    status="declined",
                    decline_reason="Ensemble synthesis approved",
                )
                if not no_clean:
                    state.delete_exploration(conn, replica["id"])
                notify(f"  Cleaned up replica: {replica['id']}")

    # Auto-clean: remove DB record (archive is the permanent record — ADR-032)
    if not no_clean:
        state.delete_exploration(conn, exploration_id)

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
    elmer_dir: Path, project_dir: Path, exploration_id: str, *,
    reason: Optional[str] = None, no_clean: bool = False, notify=None,
) -> None:
    """Decline an exploration: delete branch and clean up.

    By default, deletes the DB record after declining (ADR-032). The
    archive at .elmer/proposals/ is the permanent record.

    If reason is provided, it is stored in the archive metadata.
    Decline reasons feed into digest synthesis and future topic generation.
    """
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

    # Archive proposal before cleanup (ADR-033)
    _archive_proposal(
        elmer_dir, exp, "declined",
        project_dir=project_dir, decline_reason=reason, notify=notify,
    )

    _cleanup_worktree(project_dir, exp)

    update_fields: dict = {"status": "declined"}
    if reason:
        update_fields["decline_reason"] = reason
    state.update_exploration(conn, exploration_id, **update_fields)

    # Ensemble cascade: when declining a synthesis, decline all replicas too.
    # Replica proposals are NOT archived — synthesis is the record (ADR-036).
    # Sleep before every worktree removal — including the first.
    ens_role = exp["ensemble_role"] if "ensemble_role" in exp.keys() else None
    ens_id = exp["ensemble_id"] if "ensemble_id" in exp.keys() else None
    if ens_role == "synthesis" and ens_id:
        replicas = state.get_ensemble_replicas(conn, ens_id)
        cascade_reason = reason or "Ensemble synthesis declined"
        for replica in replicas:
            if replica["status"] not in ("approved", "declined"):
                time.sleep(1.0)
                _cleanup_worktree(project_dir, replica)
                state.update_exploration(
                    conn, replica["id"],
                    status="declined",
                    decline_reason=cascade_reason,
                )
                if not no_clean:
                    state.delete_exploration(conn, replica["id"])
                notify(f"  Cleaned up replica: {replica['id']}")

    _warn_orphaned_dependents(conn, exploration_id, notify=notify)

    # Auto-clean: remove DB record (archive is the permanent record — ADR-032)
    if not no_clean:
        state.delete_exploration(conn, exploration_id)

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
    """Cancel a running or pending exploration: stop the process, clean up.

    Sets status to 'failed' (not 'declined') so the exploration is retryable.
    Cancelled explorations should not pollute digest synthesis or trigger
    on_decline chain actions.
    """
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
        _archive_proposal(
            elmer_dir, exp, "cancelled",
            project_dir=project_dir, notify=notify,
        )

        _cleanup_worktree(project_dir, exp)
        state.update_exploration(
            conn,
            exploration_id,
            status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            **cost_fields,
        )
    else:
        # Pending — no process or worktree to clean
        state.update_exploration(conn, exploration_id, status="failed")

    _warn_orphaned_dependents(conn, exploration_id, notify=notify)
    conn.close()


def approve_all(
    elmer_dir: Path,
    project_dir: Path,
    *,
    auto_followup: bool = False,
    followup_count: int = 3,
    followup_auto_approve: bool = False,
    no_clean: bool = False,
) -> list[str]:
    """Approve all explorations with status 'done'. Returns list of approved IDs."""
    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn, status="done")
    conn.close()

    # Skip ensemble replicas — only approve synthesis or standalone
    reviewable = [
        exp for exp in explorations
        if not (exp["ensemble_role"] == "replica"
                if "ensemble_role" in exp.keys() else False)
    ]

    approved = []
    for exp in reviewable:
        try:
            approve_exploration(
                elmer_dir, project_dir, exp["id"],
                auto_followup=auto_followup,
                followup_count=followup_count,
                followup_auto_approve=followup_auto_approve,
                no_clean=no_clean,
            )
            approved.append(exp["id"])
        except SystemExit:
            # Abort the failed merge so subsequent approvals aren't poisoned
            worktree.abort_merge(project_dir)
            click.echo(f"Skipping {exp['id']} (merge failed)")
    return approved


def _rebuild_plan_dependencies(
    elmer_dir: Path,
    plan_id: str,
    *,
    notify=None,
) -> int:
    """Rebuild dependency records for all explorations in a plan from the plan JSON.

    After retrying a plan step, the old exploration (and its dependency records)
    is deleted. This leaves dependents with dangling references. This function
    reconstructs the correct dependency graph from the plan's step definitions
    and resets cascade-failed dependents to 'pending' so they can be scheduled
    when their dependencies are met (ADR-049).

    Returns the number of dependents reset to pending.
    """
    if notify is None:
        notify = lambda msg: None

    conn = state.get_db(elmer_dir)
    plan = state.get_plan(conn, plan_id)
    if plan is None:
        conn.close()
        return 0

    try:
        plan_json = json.loads(plan["plan_json"])
    except (json.JSONDecodeError, KeyError):
        conn.close()
        return 0

    steps = plan_json.get("steps", [])
    plan_exps = state.get_plan_explorations(conn, plan_id)

    # Build step_index -> exploration mapping
    exp_by_step: dict[int, dict] = {}
    for e in plan_exps:
        step_idx = e["plan_step"]
        if step_idx is not None:
            exp_by_step[step_idx] = dict(e)

    reset_count = 0

    for i, step_def in enumerate(steps):
        exp = exp_by_step.get(i)
        if exp is None:
            continue

        exp_id = exp["id"]

        # Clear existing dependency records for this exploration
        conn.execute(
            "DELETE FROM dependencies WHERE exploration_id = ?", (exp_id,)
        )

        # Rebuild from plan JSON depends_on
        step_deps = step_def.get("depends_on", [])
        for dep_idx in step_deps:
            dep_exp = exp_by_step.get(dep_idx)
            if dep_exp is not None:
                state.add_dependency(conn, exp_id, dep_exp["id"])

        # Reset cascade-failed dependents to pending
        if (
            exp["status"] == "failed"
            and (exp.get("proposal_summary") or "").startswith("(dependency failed:")
        ):
            state.update_exploration(
                conn, exp_id,
                status="pending",
                completed_at=None,
                proposal_summary=None,
            )
            reset_count += 1
            notify(f"  Reset cascade-failed step {exp.get('plan_step', '?')} ({exp_id}) to pending")

    conn.commit()
    conn.close()
    return reset_count


def retry_exploration(
    elmer_dir: Path, project_dir: Path, exploration_id: str, *, notify=None,
) -> str:
    """Retry a failed exploration or re-run a completed synthesis.

    For failed explorations: cleans up old state and re-spawns with same parameters.
    For done synthesis explorations: archives the existing synthesis and re-runs
    with the current archetype, passing the previous synthesis as context for
    the new agent to deepen.

    Returns the new exploration slug.
    """
    if notify is None:
        notify = click.echo

    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)

    if exp is None:
        click.echo(f"Exploration '{exploration_id}' not found.", err=True)
        sys.exit(1)

    # Preserve ensemble metadata for retry
    ensemble_id = exp["ensemble_id"] if "ensemble_id" in exp.keys() else None
    ensemble_role = exp["ensemble_role"] if "ensemble_role" in exp.keys() else None

    # Allow retry of done synthesis (re-synthesis), not just failed explorations
    is_resynthesis = (
        exp["status"] == "done"
        and ensemble_role == "synthesis"
        and ensemble_id
    )

    if exp["status"] != "failed" and not is_resynthesis:
        click.echo(
            f"Cannot retry exploration in status '{exp['status']}'. "
            f"Must be 'failed' (or 'done' for synthesis re-runs).",
            err=True,
        )
        sys.exit(1)

    # Extract parameters from the exploration
    topic = exp["topic"]
    archetype = exp["archetype"]
    model = exp["model"]
    max_turns = exp["max_turns"] or 50
    auto_approve = bool(exp["auto_approve"])
    generate_prompt = bool(exp["generate_prompt"])
    budget_usd = exp["budget_usd"]
    setup_cmd = exp["setup_cmd"] if "setup_cmd" in exp.keys() else None
    verify_cmd_orig = exp["verify_cmd"] if "verify_cmd" in exp.keys() else None
    plan_id = exp["plan_id"] if "plan_id" in exp.keys() else None
    plan_step = exp["plan_step"] if "plan_step" in exp.keys() else None

    # Failure-aware retry (ADR-045): inject previous failure diagnosis so
    # the agent doesn't repeat the same mistake
    failure_context = ""
    if exp["status"] == "failed" and exp.get("proposal_summary"):
        failure_reason = exp["proposal_summary"]
        # Also check log for more detail
        log_path = elmer_dir / "logs" / f"{exploration_id}.log"
        log_diagnosis = review.parse_log_details(log_path) if log_path.exists() else None
        log_snippet = ""
        if log_diagnosis and log_diagnosis.get("result_snippet"):
            log_snippet = f"\n\nFinal session output (excerpt):\n```\n{log_diagnosis['result_snippet'][:500]}\n```"

        failure_context = (
            f"\n\n## Previous Attempt Failed\n\n"
            f"This is a **retry**. The previous attempt failed with:\n"
            f"- Reason: {failure_reason}\n"
            f"{log_snippet}\n\n"
            f"**Avoid the approach that caused this failure.** If the failure was "
            f"a missing dependency, install it first. If the failure was a wrong "
            f"file path, verify paths before writing. If verification failed, "
            f"check the verification command output carefully.\n"
        )

    # For re-synthesis: capture previous synthesis content before cleanup
    previous_synthesis = None
    if is_resynthesis:
        wt_path = Path(exp["worktree_path"])
        proposal_path = wt_path / "PROPOSAL.md"
        if proposal_path.exists():
            previous_synthesis = proposal_path.read_text()
        notify(f"Re-synthesizing ensemble (previous synthesis archived)")

    # Archive proposal before cleanup (ADR-033)
    _archive_proposal(
        elmer_dir, exp, "retried",
        project_dir=project_dir, notify=notify,
    )

    # Clean up the exploration's worktree and branch
    _cleanup_worktree(project_dir, exp)
    state.delete_exploration(conn, exploration_id)
    conn.close()

    # Re-spawn: synthesis retries re-trigger synthesize_ensemble(),
    # replica/standalone retries use start_exploration().
    # Synthesis model is resolved from config (not replayed from the failed run)
    # so that config changes take effect on retry.
    if ensemble_role == "synthesis" and ensemble_id:
        slug = synth_mod.synthesize_ensemble(
            ensemble_id=ensemble_id,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            max_turns=max_turns,
            previous_synthesis=previous_synthesis,
        )
    else:
        retry_topic = topic + failure_context if failure_context else topic
        slug, _ = explore_mod.start_exploration(
            topic=retry_topic,
            archetype=archetype,
            model=model,
            max_turns=max_turns,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            auto_approve=auto_approve,
            generate_prompt=generate_prompt,
            budget_usd=budget_usd,
            setup_cmd=setup_cmd,
            verify_cmd=verify_cmd_orig,
            plan_id=plan_id,
            plan_step=plan_step,
        )

        # Restore ensemble membership on the new exploration
        if ensemble_id and ensemble_role:
            conn = state.get_db(elmer_dir)
            state.update_exploration(
                conn, slug,
                ensemble_id=ensemble_id,
                ensemble_role=ensemble_role,
            )
            conn.close()

    # Rebuild plan dependency graph after retry (ADR-049): the old exploration's
    # dependency records were deleted. Rebuild from plan JSON so dependents
    # correctly reference the new exploration, and reset cascade-failed
    # dependents to pending so they can be scheduled.
    if plan_id:
        reset = _rebuild_plan_dependencies(elmer_dir, plan_id, notify=notify)
        if reset:
            notify(f"  Reset {reset} cascade-failed dependent(s) to pending")

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

            # Preserve ensemble metadata for retry
            ensemble_id = exp["ensemble_id"] if "ensemble_id" in exp.keys() else None
            ensemble_role = exp["ensemble_role"] if "ensemble_role" in exp.keys() else None

            # Archive and clean up old state (ADR-033)
            _archive_proposal(
                elmer_dir, exp, "retried",
                project_dir=project_dir, notify=notify,
            )
            _cleanup_worktree(project_dir, exp)
            conn = state.get_db(elmer_dir)
            state.delete_exploration(conn, exp["id"])
            conn.close()

            # Synthesis retries re-trigger synthesize_ensemble();
            # replica/standalone retries use start_exploration()
            if ensemble_role == "synthesis" and ensemble_id:
                slug = synth_mod.synthesize_ensemble(
                    ensemble_id=ensemble_id,
                    elmer_dir=elmer_dir,
                    project_dir=project_dir,
                    model=model,
                    max_turns=max_turns,
                )
            else:
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

                # Restore ensemble membership on the retried exploration
                if ensemble_id and ensemble_role:
                    conn = state.get_db(elmer_dir)
                    state.update_exploration(
                        conn, slug,
                        ensemble_id=ensemble_id,
                        ensemble_role=ensemble_role,
                    )
                    conn.close()

            retried.append(slug)
            if dep_list:
                notify(f"Queued:   {slug} (waiting for {dep_list[0]})")
            else:
                notify(f"Retrying: {slug}")
        except (RuntimeError, FileNotFoundError) as e:
            notify(f"Error retrying {exp['id']}: {e}")

    return retried


def clean_preview(elmer_dir: Path) -> list[dict]:
    """Preview what clean_all would remove. Returns list of items without executing.

    Each item is a dict with 'id', 'status', 'topic', and 'has_worktree' fields.
    """
    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn)
    conn.close()

    items = []
    for exp in explorations:
        if exp["status"] in ("approved", "declined", "failed"):
            worktree_path = Path(exp["worktree_path"])
            items.append({
                "id": exp["id"],
                "status": exp["status"],
                "topic": exp["topic"],
                "has_worktree": worktree_path.exists(),
            })
    return items


def clean_all(elmer_dir: Path, project_dir: Path) -> int:
    """Clean up worktrees for completed explorations. Returns count cleaned."""
    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn)

    cleaned = 0
    worktrees_removed = 0
    for exp in explorations:
        if exp["status"] in ("approved", "declined", "failed"):
            # Archive proposal before cleanup (ADR-033)
            _archive_proposal(
                elmer_dir, exp, exp["status"],
                project_dir=project_dir,
            )

            worktree_path = Path(exp["worktree_path"])
            if worktree_path.exists():
                if worktrees_removed > 0:
                    time.sleep(1.0)  # Let IDE file watchers drain between removals
                _cleanup_worktree(project_dir, exp)
                worktrees_removed += 1
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
