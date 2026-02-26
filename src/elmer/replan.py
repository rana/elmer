"""Plan revision — mid-execution replanning when step failures reveal structural problems.

When a step failure indicates the plan itself is wrong (not just the implementation),
this module invokes a replan meta-agent to produce a revised plan, then applies the
revision by remapping explorations, cancelling dropped steps, creating new steps,
and rebuilding the dependency graph. ADR-067.
"""

import json
from pathlib import Path
from typing import Optional

import click

from . import config, explore as explore_mod, state, worker, worktree as wt_mod
from .decompose import _parse_plan_json, validate_plan


def _build_replan_prompt(
    plan_json: dict,
    failed_step_index: int,
    failure_context: str,
    approved_steps: list[dict],
    elmer_dir: Path,
    plan_id: str,
) -> str:
    """Build the prompt for the replan meta-agent."""

    steps = plan_json.get("steps", [])
    failed_step = steps[failed_step_index] if failed_step_index < len(steps) else {}

    # Build approved step summaries
    approved_summaries = []
    for info in approved_steps:
        approved_summaries.append(
            f"- Step {info['step_index']}: {info['title']} [APPROVED]\n"
            f"  Summary: {info.get('summary', '(no summary)')}"
        )

    # Build status of all steps
    step_statuses = []
    conn = state.get_db(elmer_dir)
    plan_exps = state.get_plan_explorations(conn, plan_id)
    exp_by_step = {e["plan_step"]: e for e in plan_exps}
    conn.close()

    for i, step in enumerate(steps):
        exp = exp_by_step.get(i)
        status = exp["status"] if exp else "not created"
        step_statuses.append(f"  {i}. {step.get('title', '(untitled)')} [{status}]")

    prompt = (
        f"## Plan Revision Request\n\n"
        f"The following implementation plan has a structural problem. "
        f"Step {failed_step_index} failed in a way that suggests the plan "
        f"itself needs revision, not just the implementation.\n\n"
        f"### Original Plan\n\n"
        f"```json\n{json.dumps(plan_json, indent=2)}\n```\n\n"
        f"### Step Statuses\n\n"
        + "\n".join(step_statuses) + "\n\n"
        f"### Failed Step (Step {failed_step_index})\n\n"
        f"Title: {failed_step.get('title', '(untitled)')}\n"
        f"Topic: {failed_step.get('topic', '(no topic)')[:500]}\n"
        f"Verify: {failed_step.get('verify_cmd', '(none)')}\n\n"
        f"### Failure Context\n\n{failure_context}\n\n"
        f"### Approved Steps (cannot be dropped)\n\n"
        + ("\n".join(approved_summaries) if approved_summaries else "(none)") + "\n\n"
        f"### Instructions\n\n"
        f"Produce a revised plan JSON. Preserve all approved steps (map them "
        f"with `preserved_from`). Fix the structural issue that caused step "
        f"{failed_step_index} to fail. Minimize changes — only revise what's "
        f"necessary to fix the problem.\n"
    )

    return prompt


def invoke_replan_agent(
    *,
    plan_json: dict,
    failed_step_index: int,
    failure_context: str,
    approved_steps: list[dict],
    elmer_dir: Path,
    project_dir: Path,
    plan_id: str,
    model: Optional[str] = None,
    max_turns: int = 30,
) -> dict:
    """Invoke the replan meta-agent and return the revised plan dict."""
    cfg = config.load_config(elmer_dir)
    impl_cfg = cfg.get("implement", {})
    model = model or impl_cfg.get("decompose_model", "opus")
    max_turns = impl_cfg.get("decompose_max_turns", max_turns)

    prompt = _build_replan_prompt(
        plan_json, failed_step_index, failure_context,
        approved_steps, elmer_dir, plan_id,
    )

    agent_config = config.resolve_meta_agent(project_dir, "replan")

    result = worker.run_claude(
        prompt=prompt,
        cwd=project_dir,
        model=model,
        max_turns=max_turns,
        agent_config=agent_config,
    )

    # Record cost
    conn = state.get_db(elmer_dir)
    state.record_meta_cost(
        conn,
        operation="replan",
        model=model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
    )
    conn.close()

    if not result.output:
        raise RuntimeError("Replan agent produced no output")

    return _parse_plan_json(result.output)


def validate_revision(
    revised_plan: dict,
    original_plan: dict,
    approved_step_indices: set[int],
    project_dir: Path,
) -> list[str]:
    """Validate a revised plan for structural correctness and approved-step preservation."""
    errors = validate_plan(revised_plan, project_dir)

    step_mapping = revised_plan.get("step_mapping", {})

    # Check that all approved steps are preserved
    for orig_idx in approved_step_indices:
        mapped = step_mapping.get(str(orig_idx))
        if mapped is None:
            errors.append(
                f"approved step {orig_idx} is dropped in revision "
                f"(approved work cannot be undone)"
            )

    # Check step_mapping values are valid new indices
    revised_steps = revised_plan.get("steps", [])
    num_revised = len(revised_steps)
    seen_new_indices: set[int] = set()
    for orig_str, new_idx in step_mapping.items():
        if new_idx is None:
            continue  # dropped step
        if not isinstance(new_idx, int):
            errors.append(f"step_mapping[{orig_str}] = {new_idx!r} is not an int or null")
            continue
        if new_idx < 0 or new_idx >= num_revised:
            errors.append(f"step_mapping[{orig_str}] = {new_idx} is out of range (0-{num_revised - 1})")
        if new_idx in seen_new_indices:
            errors.append(f"step_mapping maps multiple original steps to new index {new_idx}")
        seen_new_indices.add(new_idx)

    # Check preserved_from references are valid
    for i, step in enumerate(revised_steps):
        pf = step.get("preserved_from")
        if pf is not None:
            if pf not in approved_step_indices:
                errors.append(
                    f"revised step {i}: preserved_from={pf} but original step {pf} "
                    f"is not approved"
                )

    return errors


def apply_revision(
    *,
    plan_id: str,
    revised_plan: dict,
    elmer_dir: Path,
    project_dir: Path,
    failed_step_index: int,
    auto_approve: bool = True,
    model: Optional[str] = None,
    max_turns: int = 50,
    notify=None,
) -> dict:
    """Apply a revised plan to an existing plan's state.

    This is the core state transition:
    1. Archive the old plan JSON
    2. Cancel/delete non-approved explorations that are dropped
    3. Remap preserved explorations to new step indices
    4. Create new explorations for new steps
    5. Rebuild dependency graph
    6. Resume the plan

    Returns a summary dict with counts of actions taken.
    """
    if notify is None:
        notify = click.echo

    conn = state.get_db(elmer_dir)
    plan = state.get_plan(conn, plan_id)
    if plan is None:
        conn.close()
        raise RuntimeError(f"Plan '{plan_id}' not found")

    original_plan = json.loads(plan["plan_json"])
    original_steps = original_plan.get("steps", [])
    revised_steps = revised_plan.get("steps", [])
    step_mapping = revised_plan.get("step_mapping", {})

    # Get current explorations
    plan_exps = state.get_plan_explorations(conn, plan_id)
    exp_by_step: dict[int, dict] = {}
    for e in plan_exps:
        if e["plan_step"] is not None:
            exp_by_step[e["plan_step"]] = dict(e)

    summary = {
        "preserved": 0,
        "cancelled": 0,
        "remapped": 0,
        "created": 0,
        "total_new_steps": len(revised_steps),
    }

    conn.close()

    # Phase 1: Cancel explorations for dropped steps
    for orig_idx_str, new_idx in step_mapping.items():
        orig_idx = int(orig_idx_str)
        if new_idx is not None:
            continue  # not dropped

        exp = exp_by_step.get(orig_idx)
        if exp is None:
            continue

        if exp["status"] in ("running", "pending", "amending"):
            from . import gate  # late import to avoid circular
            try:
                gate.cancel_exploration(
                    elmer_dir, project_dir, exp["id"], notify=notify,
                )
                summary["cancelled"] += 1
                notify(f"  Cancelled dropped step {orig_idx}: {exp['id']}")
            except (RuntimeError, SystemExit):
                # Already in terminal state, just delete
                conn = state.get_db(elmer_dir)
                state.delete_exploration(conn, exp["id"])
                conn.close()
                summary["cancelled"] += 1
        elif exp["status"] == "failed":
            # Clean up failed exploration
            conn = state.get_db(elmer_dir)
            state.delete_exploration(conn, exp["id"])
            conn.close()
            summary["cancelled"] += 1
            notify(f"  Removed dropped failed step {orig_idx}: {exp['id']}")

    # Also cancel explorations for original steps not mentioned in mapping at all
    mapped_orig_indices = {int(k) for k in step_mapping}
    for orig_idx, exp in exp_by_step.items():
        if orig_idx in mapped_orig_indices:
            continue
        if exp["status"] in ("running", "pending", "amending", "failed"):
            from . import gate
            try:
                gate.cancel_exploration(
                    elmer_dir, project_dir, exp["id"], notify=notify,
                )
            except (RuntimeError, SystemExit):
                conn = state.get_db(elmer_dir)
                state.delete_exploration(conn, exp["id"])
                conn.close()
            summary["cancelled"] += 1
            notify(f"  Cancelled unmapped step {orig_idx}: {exp['id']}")

    # Phase 2: Remap preserved/approved explorations to new step indices
    for orig_idx_str, new_idx in step_mapping.items():
        orig_idx = int(orig_idx_str)
        if new_idx is None:
            continue

        exp = exp_by_step.get(orig_idx)
        if exp is None:
            continue

        if exp["status"] == "approved":
            # Approved step: just update the step index
            conn = state.get_db(elmer_dir)
            state.update_exploration(conn, exp["id"], plan_step=new_idx)
            conn.close()
            summary["preserved"] += 1
            notify(f"  Preserved step {orig_idx} -> {new_idx}: {exp['id']}")
        elif exp["status"] in ("done", "running", "amending", "pending"):
            # Non-approved but still active: remap
            conn = state.get_db(elmer_dir)
            state.update_exploration(conn, exp["id"], plan_step=new_idx)
            conn.close()
            summary["remapped"] += 1
            notify(f"  Remapped step {orig_idx} -> {new_idx}: {exp['id']}")

    # Phase 3: Create explorations for genuinely new steps
    cfg = config.load_config(elmer_dir)
    impl_cfg = cfg.get("implement", {})
    default_model = model or impl_cfg.get("model", cfg.get("defaults", {}).get("model", "opus"))
    default_max_turns = impl_cfg.get("max_turns", max_turns)

    # Determine which new step indices already have explorations
    conn = state.get_db(elmer_dir)
    plan_exps_after = state.get_plan_explorations(conn, plan_id)
    conn.close()
    existing_new_steps = {e["plan_step"] for e in plan_exps_after if e["plan_step"] is not None}

    from . import implement as impl_mod  # late import

    for i, step in enumerate(revised_steps):
        if i in existing_new_steps:
            continue  # Already has an exploration (preserved or remapped)

        if step.get("preserved_from") is not None:
            continue  # Placeholder for approved work — skip

        # Build dependencies from revised plan
        step_deps = step.get("depends_on", [])
        # Resolve dep indices to exploration IDs
        conn = state.get_db(elmer_dir)
        plan_exps_current = state.get_plan_explorations(conn, plan_id)
        conn.close()
        exp_by_new_step = {e["plan_step"]: e for e in plan_exps_current if e["plan_step"] is not None}
        depends_on: list[str] = []
        for dep_idx in step_deps:
            dep_exp = exp_by_new_step.get(dep_idx)
            if dep_exp is not None:
                depends_on.append(dep_exp["id"])

        archetype = step.get("archetype", "implement")
        verify_cmd = step.get("verify_cmd")
        setup_cmd = step.get("setup_cmd")
        step_model = step.get("model", default_model)

        # Build step context with revision awareness
        step_context = impl_mod._build_step_context(
            elmer_dir, project_dir, plan_id, revised_plan, i,
        )

        revision_note = revised_plan.get("revision_note", "")
        revision_block = (
            f"\n\n## Plan Revision Notice\n\n"
            f"This plan was revised after step {failed_step_index} failed. "
            f"{revision_note}\n"
            f"Previous steps may reflect the original plan structure. "
            f"Focus on your specific task.\n"
        )

        verify_block = ""
        if verify_cmd:
            verify_block = (
                "\n\n## Verification\n\n"
                f"After completing your work, this command will be run to verify it:\n\n"
                f"```\n{verify_cmd}\n```\n\n"
                f"Run this command yourself before writing PROPOSAL.md. "
                f"If it fails, fix the issues — do not skip or remove tests. "
                f"Include the command output in your PROPOSAL.md."
            )

        enriched_topic = step["topic"] + verify_block + revision_block + "\n\n" + step_context

        try:
            slug, _ = explore_mod.start_exploration(
                topic=enriched_topic,
                archetype=archetype,
                model=step_model,
                max_turns=default_max_turns,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                depends_on=depends_on if depends_on else None,
                auto_approve=auto_approve,
                verify_cmd=verify_cmd,
                plan_id=plan_id,
                plan_step=i,
                setup_cmd=setup_cmd,
            )
            summary["created"] += 1
            notify(f"  Created new step {i}: {step.get('title', slug)} ({slug})")
        except (RuntimeError, FileNotFoundError) as e:
            notify(f"  FAILED to create step {i}: {e}")

    # Phase 4: Rebuild dependency graph from revised plan
    _rebuild_revised_dependencies(elmer_dir, plan_id, revised_plan, notify=notify)

    # Phase 5: Update plan record
    conn = state.get_db(elmer_dir)
    state.update_plan(
        conn, plan_id,
        plan_json=json.dumps(revised_plan),
        prior_plan_json=json.dumps(original_plan),
        revision_count=(plan["revision_count"] or 0) + 1,
        replan_trigger_step=failed_step_index,
        status="active",
        completion_note=None,
    )
    conn.close()

    return summary


def _rebuild_revised_dependencies(
    elmer_dir: Path,
    plan_id: str,
    revised_plan: dict,
    *,
    notify=None,
) -> None:
    """Rebuild dependency graph from revised plan JSON."""
    if notify is None:
        notify = lambda msg: None

    conn = state.get_db(elmer_dir)
    plan_exps = state.get_plan_explorations(conn, plan_id)
    exp_by_step: dict[int, dict] = {}
    for e in plan_exps:
        if e["plan_step"] is not None:
            exp_by_step[e["plan_step"]] = dict(e)

    revised_steps = revised_plan.get("steps", [])

    # Clear all existing dependencies for this plan's explorations
    for exp in plan_exps:
        conn.execute("DELETE FROM dependencies WHERE exploration_id = ?", (exp["id"],))

    # Rebuild from revised plan
    for i, step_def in enumerate(revised_steps):
        exp = exp_by_step.get(i)
        if exp is None:
            continue

        # Approved steps don't need dependencies (they're already done)
        if exp["status"] == "approved":
            continue

        step_deps = step_def.get("depends_on", [])
        for dep_idx in step_deps:
            dep_exp = exp_by_step.get(dep_idx)
            if dep_exp is not None:
                state.add_dependency(conn, exp["id"], dep_exp["id"])

    conn.commit()
    conn.close()


def replan(
    *,
    plan_id: str,
    failure_context: str,
    elmer_dir: Path,
    project_dir: Path,
    model: Optional[str] = None,
    auto_approve: bool = True,
    dry_run: bool = False,
    notify=None,
) -> dict:
    """Full replan workflow: diagnose, invoke agent, validate, apply.

    Returns the summary dict from apply_revision (or the revised plan
    if dry_run=True).
    """
    if notify is None:
        notify = click.echo

    conn = state.get_db(elmer_dir)
    plan = state.get_plan(conn, plan_id)
    if plan is None:
        conn.close()
        raise RuntimeError(f"Plan '{plan_id}' not found")

    if plan["status"] not in ("paused", "active"):
        conn.close()
        raise RuntimeError(
            f"Plan '{plan_id}' is {plan['status']}, not replannable "
            f"(must be paused or active)"
        )

    plan_json = json.loads(plan["plan_json"])
    steps = plan_json.get("steps", [])

    # Find the failed step(s) — use the first root-cause failure
    plan_exps = state.get_plan_explorations(conn, plan_id)
    failed_exps = [
        e for e in plan_exps
        if e["status"] == "failed"
        and not (e.get("proposal_summary") or "").startswith("(dependency failed:")
    ]

    if not failed_exps:
        conn.close()
        raise RuntimeError(
            f"Plan '{plan_id}' has no root-cause failed steps. "
            f"Use 'elmer implement --resume' to retry."
        )

    failed_exp = failed_exps[0]
    failed_step_index = failed_exp["plan_step"]

    # Build approved step info
    approved_exps = [e for e in plan_exps if e["status"] == "approved"]
    approved_step_indices = {e["plan_step"] for e in approved_exps}
    approved_steps = []
    for e in approved_exps:
        step_idx = e["plan_step"]
        step_def = steps[step_idx] if step_idx < len(steps) else {}
        approved_steps.append({
            "step_index": step_idx,
            "title": step_def.get("title", e["id"]),
            "summary": e.get("proposal_summary", ""),
        })

    conn.close()

    notify(f"Replanning: {plan_id}")
    notify(f"  Failed step: {failed_step_index} ({failed_exp['id']})")
    notify(f"  Approved steps: {sorted(approved_step_indices) if approved_step_indices else '(none)'}")
    notify(f"  Invoking replan agent...")

    # Invoke replan agent
    revised_plan = invoke_replan_agent(
        plan_json=plan_json,
        failed_step_index=failed_step_index,
        failure_context=failure_context,
        approved_steps=approved_steps,
        elmer_dir=elmer_dir,
        project_dir=project_dir,
        plan_id=plan_id,
        model=model,
    )

    # Validate
    errors = validate_revision(
        revised_plan, plan_json, approved_step_indices, project_dir,
    )
    if errors:
        notify("Revised plan has validation errors:")
        for err in errors:
            notify(f"  - {err}")
        raise RuntimeError(
            f"Revised plan has {len(errors)} validation error(s). "
            f"Replan agent produced an invalid revision."
        )

    revised_steps = revised_plan.get("steps", [])
    step_mapping = revised_plan.get("step_mapping", {})
    revision_note = revised_plan.get("revision_note", "")

    notify(f"\nRevised plan: {len(revised_steps)} steps")
    notify(f"  Revision: {revision_note}")
    for i, step in enumerate(revised_steps):
        pf = step.get("preserved_from")
        marker = " [preserved]" if pf is not None else ""
        notify(f"  {i}. {step.get('title', '(untitled)')}{marker}")

    # Show mapping
    dropped = [k for k, v in step_mapping.items() if v is None]
    if dropped:
        notify(f"  Dropped original steps: {', '.join(dropped)}")

    if dry_run:
        return revised_plan

    # Apply
    notify("\nApplying revision...")
    summary = apply_revision(
        plan_id=plan_id,
        revised_plan=revised_plan,
        elmer_dir=elmer_dir,
        project_dir=project_dir,
        failed_step_index=failed_step_index,
        auto_approve=auto_approve,
        model=model,
        notify=notify,
    )

    notify(
        f"\nPlan '{plan_id}' revised: "
        f"{summary['preserved']} preserved, "
        f"{summary['remapped']} remapped, "
        f"{summary['created']} created, "
        f"{summary['cancelled']} cancelled"
    )

    return summary
