"""Implementation execution — convert plans into explorations and orchestrate.

Handles the execution phase: creating chained explorations from plan steps,
building cross-step context for information flow between steps, and managing
the plan-to-exploration mapping. Decomposition lives in decompose.py;
plan lifecycle (status, resume, verification) lives in plan.py.
"""

import json
from pathlib import Path
from typing import Optional

import click

from . import config, explore as explore_mod, state, worktree as wt_mod
from .decompose import estimate_plan_duration, validate_prerequisites, validate_step_metadata


def _build_step_context(
    elmer_dir: Path,
    project_dir: Path,
    plan_id: str,
    plan_json: dict,
    current_step: int,
    *,
    max_context_chars: int = 12000,
) -> str:
    """Build cross-step context block for injection into a step's topic.

    Tells the implementation session where it sits in the plan, what previous
    steps accomplished, and what's coming next. This is the primary mechanism
    for information flow between steps (ADR-040).

    Context budget (ADR-044): for long plans, context grows linearly with step
    count and can overflow the claude context window. We enforce a character
    budget by prioritizing recent/dependency steps with full detail and
    compressing older steps to one-line summaries.
    """
    steps = plan_json.get("steps", [])
    milestone = plan_json.get("milestone", "unknown")
    lines = [
        f"## Implementation Plan Context",
        f"",
        f"This is **Step {current_step} of {len(steps)}** in milestone \"{milestone}\".",
        f"Plan ID: {plan_id}",
        f"",
    ]

    # Revision awareness (ADR-067)
    revision_note = plan_json.get("revision_note")
    if revision_note:
        lines.append(
            f"**NOTE: This plan was revised.** {revision_note}"
        )
        lines.append("")

    # Query step statuses from DB
    conn = state.get_db(elmer_dir)
    plan_exps = state.get_plan_explorations(conn, plan_id)
    exp_by_step = {e["plan_step"]: e for e in plan_exps}

    # Determine which previous steps get full detail vs one-line summary.
    step_deps = set(steps[current_step].get("depends_on", [])) if current_step < len(steps) else set()
    recent_window = max(0, current_step - 3)
    def _is_detailed(idx: int) -> bool:
        return idx >= recent_window or idx in step_deps

    # Previous steps summary
    artifact_lines: list[str] = []
    artifact_step_limit = 3
    artifact_steps_collected = 0

    if current_step > 0:
        lines.append("### Previous Steps")
        lines.append("")
        for i in range(current_step):
            step_def = steps[i] if i < len(steps) else {}
            title = step_def.get("title", f"Step {i}")
            exp = exp_by_step.get(i)

            if not _is_detailed(i):
                status = exp["status"] if exp else "not created"
                lines.append(f"- Step {i}: {title} [{status}]")
                continue

            if exp:
                status = exp["status"]
                icon = {"approved": "+", "done": "*", "running": "~",
                        "failed": "!", "pending": "."}.get(status, "?")
                lines.append(f"- {icon} Step {i}: {title} [{status}]")

                if status in ("approved", "done") and exp.get("proposal_summary"):
                    summary = exp["proposal_summary"]
                    if len(summary) > 200:
                        summary = summary[:200] + "..."
                    lines.append(f"  Summary: {summary}")

                if status == "approved":
                    try:
                        branch = exp["branch"]
                        diff = wt_mod.get_branch_diff(project_dir, branch)
                        if diff:
                            file_lines = [l.strip().split("|")[0].strip()
                                          for l in diff.strip().splitlines()
                                          if "|" in l][:10]
                            if file_lines:
                                lines.append(f"  Files changed: {', '.join(file_lines)}")
                    except Exception:
                        pass

                    if artifact_steps_collected < artifact_step_limit:
                        key_files = step_def.get("key_files", [])
                        for kf in key_files:
                            kf_path = project_dir / kf
                            if kf_path.exists():
                                try:
                                    content = kf_path.read_text()
                                    if len(content) > 2000:
                                        content = content[:2000] + "\n... (truncated)"
                                    artifact_lines.append(
                                        f"#### {kf} (from Step {i})\n\n```\n{content}\n```"
                                    )
                                except Exception:
                                    pass
                        if key_files:
                            artifact_steps_collected += 1
            else:
                lines.append(f"- Step {i}: {title} [not yet created]")
        lines.append("")

    # Append key file artifacts after step summary
    if artifact_lines:
        lines.append("### Key Files from Previous Steps")
        lines.append("")
        lines.extend(artifact_lines)
        lines.append("")

    # Upcoming steps summary
    remaining = [s for idx, s in enumerate(steps) if idx > current_step]
    if remaining:
        lines.append("### Upcoming Steps")
        lines.append("")
        for idx, s in enumerate(steps):
            if idx <= current_step:
                continue
            lines.append(f"- Step {idx}: {s.get('title', '(untitled)')}")
        lines.append("")

    conn.close()

    # Enforce context budget
    result = "\n".join(lines)
    if len(result) > max_context_chars:
        lines_no_artifacts = [l for l in lines
                              if not l.startswith("#### ") and not l.startswith("```")]
        result = "\n".join(lines_no_artifacts)
        if len(result) > max_context_chars:
            result = result[:max_context_chars] + "\n... (context truncated)"

    return result


def execute_plan(
    *,
    plan: dict,
    elmer_dir: Path,
    project_dir: Path,
    model: Optional[str] = None,
    max_turns: int = 50,
    auto_approve: bool = True,
    max_concurrent: int = 1,
    step_filter: Optional[list[int]] = None,
) -> str:
    """Convert a plan into chained explorations and launch.

    If step_filter is provided, only those step indices are created.
    Returns the plan_id for tracking.
    """
    cfg = config.load_config(elmer_dir)
    impl_cfg = cfg.get("implement", {})
    model = model or impl_cfg.get("model", cfg.get("defaults", {}).get("model", "opus"))
    max_turns = impl_cfg.get("max_turns", max_turns)

    milestone_ref = plan.get("milestone", "unknown")
    steps = plan.get("steps", [])

    if not steps:
        raise RuntimeError("Plan has no implementation steps")

    # Pre-flight prerequisite validation (ADR-042)
    failures = validate_prerequisites(plan, project_dir)
    if failures:
        click.echo("\nPrerequisite check failed:", err=True)
        for f in failures:
            click.echo(f"  - {f}", err=True)
        raise RuntimeError(
            f"Plan has {len(failures)} unmet prerequisite(s). "
            "Fix these before executing, or remove 'prerequisites' from the plan."
        )

    # Step metadata completeness warnings
    meta_warnings = validate_step_metadata(plan)
    for w in meta_warnings:
        click.echo(f"  Metadata warning: {w}", err=True)

    # Duration estimate check (ADR-061)
    total_seconds, dur_warnings = estimate_plan_duration(plan)
    if total_seconds is not None:
        total_hours = total_seconds / 3600
        click.echo(f"  Estimated runtime: {total_hours:.1f}h ({len(steps)} steps)")
        cfg = config.load_config(elmer_dir)
        max_hours = cfg.get("implement", {}).get("max_plan_hours")
        if max_hours and total_hours > max_hours:
            click.echo(
                f"  Warning: estimated runtime ({total_hours:.1f}h) exceeds "
                f"max_plan_hours ({max_hours}h)",
                err=True,
            )
    for w in dur_warnings:
        click.echo(f"  Duration warning: {w}", err=True)

    # Generate plan ID from milestone ref
    plan_id = explore_mod.slugify(milestone_ref) or "plan"
    conn = state.get_db(elmer_dir)

    # Ensure unique plan ID
    existing = state.get_plan(conn, plan_id)
    if existing:
        counter = 2
        while state.get_plan(conn, f"{plan_id}-{counter}"):
            counter += 1
        plan_id = f"{plan_id}-{counter}"

    # Store the plan
    state.create_plan(
        conn,
        id=plan_id,
        milestone_ref=milestone_ref,
        plan_json=json.dumps(plan),
    )
    conn.close()

    # Determine which steps to execute
    indices_to_run = step_filter if step_filter else list(range(len(steps)))

    # Create explorations for each step
    exploration_ids: dict[int, str] = {}
    prev_id: Optional[str] = None

    creation_errors: list[tuple[int, str]] = []

    for i in indices_to_run:
        if i < 0 or i >= len(steps):
            click.echo(f"  Step {i}: out of range (0-{len(steps) - 1}), skipping", err=True)
            continue

        step = steps[i]

        # Determine dependencies
        step_deps = step.get("depends_on", [])
        depends_on: list[str] = []

        if step_deps:
            for dep_idx in step_deps:
                if dep_idx in exploration_ids:
                    depends_on.append(exploration_ids[dep_idx])
        elif prev_id is not None and max_concurrent == 1:
            depends_on.append(prev_id)

        archetype = step.get("archetype", "implement")
        verify_cmd = step.get("verify_cmd")
        setup_cmd = step.get("setup_cmd")

        # Per-step model routing (ADR-045, B3, ADR-074)
        # Priority: step.model (from decompose agent) > config routing > defaults > plan model
        step_model = step.get("model")
        if not step_model:
            routing = cfg.get("implement", {}).get("model_routing", {})
            # Apply sensible defaults when no config routing exists:
            # scaffold (step 0) uses opus, everything else uses sonnet
            if not routing:
                routing = {"scaffold": "opus", "fallback": "sonnet"}
            if i == 0 and "scaffold" in routing:
                step_model = routing["scaffold"]
            elif archetype in routing:
                step_model = routing[archetype]
            elif "fallback" in routing:
                step_model = routing["fallback"]
            else:
                step_model = model

        # Cross-step context injection (ADR-040)
        step_context = _build_step_context(
            elmer_dir, project_dir, plan_id, plan, i,
        )

        # Inject relevant_docs so the worker reads targeted documentation
        docs_block = ""
        relevant_docs = step.get("relevant_docs", [])
        if relevant_docs:
            doc_list = "\n".join(f"- {d}" for d in relevant_docs)
            docs_block = (
                "\n\n## Relevant Documentation\n\n"
                f"Read these documents/sections first — they contain the context "
                f"most relevant to this step. Prioritize these over reading the "
                f"full documentation set:\n\n{doc_list}"
            )

        # Inject verify_cmd so the agent knows its success criterion (ADR-043)
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

        enriched_topic = step["topic"] + docs_block + verify_block + "\n\n" + step_context

        try:
            slug, _ = explore_mod.start_exploration(
                topic=enriched_topic,
                archetype=archetype,
                model=step_model,
                max_turns=max_turns,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                depends_on=depends_on if depends_on else None,
                auto_approve=auto_approve,
                verify_cmd=verify_cmd,
                plan_id=plan_id,
                plan_step=i,
                setup_cmd=setup_cmd,
            )
            exploration_ids[i] = slug
            prev_id = slug

            click.echo(f"  Step {i}: {step.get('title', slug)}")
            click.echo(f"    ID: {slug}")
            if depends_on:
                click.echo(f"    Depends on: {', '.join(depends_on)}")
            if verify_cmd:
                click.echo(f"    Verify: {verify_cmd}")
            if step_model != model:
                click.echo(f"    Model: {step_model} (override)")

        except (RuntimeError, FileNotFoundError) as e:
            click.echo(f"  Step {i}: FAILED to create — {e}", err=True)
            creation_errors.append((i, str(e)))

    # If some steps failed to create, pause the plan to prevent the daemon
    # from scheduling a plan with gaps (ADR-062: partial plan rollback).
    if creation_errors and exploration_ids:
        conn = state.get_db(elmer_dir)
        state.update_plan(conn, plan_id, status="paused")
        conn.close()
        click.echo(
            f"\nWarning: {len(creation_errors)} step(s) failed to create. "
            f"Plan paused to prevent execution with gaps.",
            err=True,
        )
        for step_idx, err in creation_errors:
            click.echo(f"  Step {step_idx}: {err}", err=True)
        click.echo(
            f"Fix the issues and use 'elmer implement --load-plan ... --steps {','.join(str(i) for i, _ in creation_errors)}' "
            f"to retry failed steps.",
            err=True,
        )
    elif creation_errors and not exploration_ids:
        # All steps failed — mark plan as failed entirely
        conn = state.get_db(elmer_dir)
        state.update_plan(conn, plan_id, status="failed")
        conn.close()
        click.echo(f"\nPlan {plan_id}: all steps failed to create — plan marked failed", err=True)

    click.echo(f"\nPlan {plan_id}: {len(exploration_ids)} step(s) created")
    if step_filter:
        click.echo(f"  (partial execution: steps {step_filter})")
    return plan_id
