"""Implementation orchestration — decompose milestones, execute plans, verify results.

Composes existing primitives (explore, batch, amend, approve) with new capabilities:
- Milestone decomposition via meta-agent
- Per-step verification hooks
- Auto-amend on verification failure
- Plan tracking and reporting
- Cross-step context injection (ADR-040)
- Plan loading from saved files
"""

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from . import config, explore as explore_mod, state, worker, worktree as wt_mod


def _read_project_context(project_dir: Path) -> str:
    """Read CLAUDE.md for context injection into decompose prompt.

    Only injects CLAUDE.md (orientation/tech stack). The decompose agent
    reads ROADMAP.md, DESIGN.md, and DECISIONS.md selectively via its own
    tools to avoid blowing the context window on large doc sets.
    """
    sections = []
    # CLAUDE.md is always small enough and provides essential orientation
    claude_md = project_dir / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        if len(content) > 20000:
            content = content[:20000] + "\n... (truncated)"
        sections.append(f"## CLAUDE.md\n\n{content}")

    # List which other docs exist so the agent knows what to read
    doc_files = []
    for name in ["CONTEXT.md", "DESIGN.md", "DESIGN-arc1.md", "DESIGN-arc2-3.md",
                  "DESIGN-arc4-plus.md", "DECISIONS.md", "DECISIONS-core.md",
                  "DECISIONS-experience.md", "DECISIONS-operations.md",
                  "ROADMAP.md", "PRINCIPLES.md"]:
        path = project_dir / name
        if path.exists():
            size_kb = path.stat().st_size // 1024
            doc_files.append(f"- {name} ({size_kb}KB)")
    if doc_files:
        sections.append(
            "## Available Documentation\n\n"
            "Read these selectively via your tools — do NOT try to read all of them.\n\n"
            + "\n".join(doc_files)
        )

    return "\n\n---\n\n".join(sections)


def _scan_filesystem(project_dir: Path) -> str:
    """Produce a compact listing of what exists in the project."""
    lines = []
    for item in sorted(project_dir.iterdir()):
        if item.name.startswith("."):
            continue
        if item.is_dir():
            lines.append(f"  {item.name}/")
            # One level deep
            try:
                children = sorted(item.iterdir())[:20]
                for child in children:
                    if child.name.startswith("."):
                        continue
                    suffix = "/" if child.is_dir() else ""
                    lines.append(f"    {child.name}{suffix}")
                if len(list(item.iterdir())) > 20:
                    lines.append(f"    ... ({len(list(item.iterdir()))} items)")
            except PermissionError:
                pass
        else:
            lines.append(f"  {item.name}")
    return "\n".join(lines) if lines else "  (empty project directory)"


def _parse_plan_json(raw_output: str) -> dict:
    """Extract JSON plan from meta-agent output, handling markdown fencing."""
    # Strip markdown code fences if present
    cleaned = raw_output.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    # Find the JSON object
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No JSON object found in decomposition output")

    # Find matching closing brace
    depth = 0
    for i, ch in enumerate(cleaned[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start:i + 1])

    raise ValueError("Malformed JSON in decomposition output")


def decompose_milestone(
    *,
    milestone_ref: str,
    elmer_dir: Path,
    project_dir: Path,
    model: Optional[str] = None,
    max_turns: int = 30,
) -> dict:
    """Decompose a milestone into implementation steps.

    Calls the decompose meta-agent with project context.
    Returns a plan dict with 'steps', 'questions', and 'milestone' keys.
    """
    cfg = config.load_config(elmer_dir)
    impl_cfg = cfg.get("implement", {})
    model = model or impl_cfg.get("decompose_model", "opus")
    max_turns = impl_cfg.get("decompose_max_turns", max_turns)

    # Build the prompt
    context = _read_project_context(project_dir)
    filesystem = _scan_filesystem(project_dir)

    prompt = (
        f"Decompose this milestone into implementation steps: {milestone_ref}\n\n"
        f"## Current Filesystem\n\n```\n{filesystem}\n```\n\n"
        f"## Project Documentation\n\n{context}"
    )

    # Resolve the decompose meta-agent
    agent_config = config.resolve_meta_agent(project_dir, "decompose")

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
        operation="decompose",
        model=model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
    )
    conn.close()

    # Parse the plan from output
    if not result.output:
        raise RuntimeError("Decompose agent produced no output")

    return _parse_plan_json(result.output)


def _inject_answers(plan: dict, answers: dict[int, str]) -> dict:
    """Inject user answers into step topics as additional context."""
    if not answers:
        return plan

    answer_block = "\n\n## Context from user\n\n"
    for q_idx, answer in sorted(answers.items()):
        if q_idx < len(plan.get("questions", [])):
            question = plan["questions"][q_idx]
            answer_block += f"Q: {question}\nA: {answer}\n\n"

    for step in plan["steps"]:
        step["topic"] = step["topic"] + answer_block

    return plan


def load_plan(plan_path: Path) -> dict:
    """Load a saved plan from a JSON file."""
    raw = plan_path.read_text()
    plan = json.loads(raw)
    if "steps" not in plan:
        raise ValueError(f"Plan file missing 'steps' key: {plan_path}")
    return plan


def validate_prerequisites(
    plan: dict,
    project_dir: Path,
) -> list[str]:
    """Validate plan prerequisites before execution. Returns list of failures.

    The decompose agent can specify prerequisites in the plan JSON:
      {
        "prerequisites": {
          "env_vars": ["NEON_DATABASE_URL", "VOYAGE_API_KEY"],
          "commands": ["node --version", "pnpm --version"],
          "files": ["DESIGN.md", "package.json"]
        }
      }

    Empty list = all prerequisites met. Non-empty = failures that block execution.
    """
    prereqs = plan.get("prerequisites", {})
    failures: list[str] = []

    # Check environment variables
    for var in prereqs.get("env_vars", []):
        if not os.environ.get(var):
            failures.append(f"env var missing: {var}")

    # Check commands are available
    for cmd in prereqs.get("commands", []):
        try:
            subprocess.run(
                cmd, shell=True, cwd=str(project_dir),
                capture_output=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            failures.append(f"command failed: {cmd}")

    # Check files exist in project
    for filepath in prereqs.get("files", []):
        if not (project_dir / filepath).exists():
            failures.append(f"file missing: {filepath}")

    return failures


def _build_step_context(
    elmer_dir: Path,
    project_dir: Path,
    plan_id: str,
    plan_json: dict,
    current_step: int,
) -> str:
    """Build cross-step context block for injection into a step's topic.

    Tells the implementation session where it sits in the plan, what previous
    steps accomplished, and what's coming next. This is the primary mechanism
    for information flow between steps (ADR-040).
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

    # Query step statuses from DB
    conn = state.get_db(elmer_dir)
    plan_exps = state.get_plan_explorations(conn, plan_id)
    exp_by_step = {e["plan_step"]: e for e in plan_exps}

    # Previous steps summary
    artifact_lines: list[str] = []  # Collect key file artifacts separately

    if current_step > 0:
        lines.append("### Previous Steps")
        lines.append("")
        for i in range(current_step):
            step_def = steps[i] if i < len(steps) else {}
            title = step_def.get("title", f"Step {i}")
            exp = exp_by_step.get(i)
            if exp:
                status = exp["status"]
                icon = {"approved": "+", "done": "*", "running": "~",
                        "failed": "!", "pending": "."}.get(status, "?")
                lines.append(f"- {icon} Step {i}: {title} [{status}]")

                # Inject proposal summary from approved/done steps
                if status in ("approved", "done") and exp.get("proposal_summary"):
                    summary = exp["proposal_summary"]
                    if len(summary) > 200:
                        summary = summary[:200] + "..."
                    lines.append(f"  Summary: {summary}")

                # Read key files changed from merged proposals (best-effort)
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

                    # Inject key file artifacts from approved steps (ADR-042)
                    key_files = step_def.get("key_files", [])
                    for kf in key_files:
                        kf_path = project_dir / kf
                        if kf_path.exists():
                            try:
                                content = kf_path.read_text()
                                # Truncate large files
                                if len(content) > 2000:
                                    content = content[:2000] + "\n... (truncated)"
                                artifact_lines.append(
                                    f"#### {kf} (from Step {i})\n\n```\n{content}\n```"
                                )
                            except Exception:
                                pass
            else:
                lines.append(f"- Step {i}: {title} [not yet created]")
        lines.append("")

    # Append key file artifacts after step summary (keeps summary scannable)
    if artifact_lines:
        lines.append("### Key Files from Previous Steps")
        lines.append("")
        lines.extend(artifact_lines)
        lines.append("")

    # Upcoming steps summary (brief, just titles)
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
    return "\n".join(lines)


def execute_plan(
    *,
    plan: dict,
    elmer_dir: Path,
    project_dir: Path,
    model: Optional[str] = None,
    max_turns: int = 50,
    auto_approve: bool = True,
    budget_usd: Optional[float] = None,
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

    # Budget: divide across steps being run
    per_step_budget = None
    if budget_usd is not None:
        per_step_budget = budget_usd / len(indices_to_run)

    # Create explorations for each step
    exploration_ids: dict[int, str] = {}  # step index -> exploration ID
    prev_id: Optional[str] = None

    for i in indices_to_run:
        if i < 0 or i >= len(steps):
            click.echo(f"  Step {i}: out of range (0-{len(steps) - 1}), skipping", err=True)
            continue

        step = steps[i]

        # Determine dependencies
        step_deps = step.get("depends_on", [])
        depends_on: list[str] = []

        if step_deps:
            # Map step indices to exploration IDs
            for dep_idx in step_deps:
                if dep_idx in exploration_ids:
                    depends_on.append(exploration_ids[dep_idx])
        elif prev_id is not None and max_concurrent == 1:
            # Default to chain mode: each step depends on previous
            depends_on.append(prev_id)

        archetype = step.get("archetype", "implement")
        verify_cmd = step.get("verify_cmd")

        # Cross-step context injection (ADR-040): tell this step about
        # the plan, what previous steps accomplished, and what's next
        step_context = _build_step_context(
            elmer_dir, project_dir, plan_id, plan, i,
        )
        enriched_topic = step["topic"] + "\n\n" + step_context

        try:
            slug, _ = explore_mod.start_exploration(
                topic=enriched_topic,
                archetype=archetype,
                model=model,
                max_turns=max_turns,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                depends_on=depends_on if depends_on else None,
                auto_approve=auto_approve,
                budget_usd=per_step_budget,
                verify_cmd=verify_cmd,
                plan_id=plan_id,
                plan_step=i,
            )
            exploration_ids[i] = slug
            prev_id = slug

            click.echo(f"  Step {i}: {step.get('title', slug)}")
            click.echo(f"    ID: {slug}")
            if depends_on:
                click.echo(f"    Depends on: {', '.join(depends_on)}")
            if verify_cmd:
                click.echo(f"    Verify: {verify_cmd}")

        except (RuntimeError, FileNotFoundError) as e:
            click.echo(f"  Step {i}: FAILED to create — {e}", err=True)

    click.echo(f"\nPlan {plan_id}: {len(exploration_ids)} step(s) created")
    if step_filter:
        click.echo(f"  (partial execution: steps {step_filter})")
    return plan_id


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
            }
            if exp["cost_usd"]:
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
        if plan.get("total_cost"):
            click.echo(f"  Cost:      ${plan['total_cost']:.2f}")
        click.echo()

        steps = plan.get("steps", [])
        if not steps:
            click.echo("  (no steps)")
            continue

        # Parse original plan for titles
        try:
            original = json.loads(plan["plan_json"])
            titles = {i: s.get("title", "") for i, s in enumerate(original.get("steps", []))}
        except (json.JSONDecodeError, KeyError):
            titles = {}

        for step in steps:
            icon = status_icons.get(step["status"], " ")
            title = titles.get(step["step"], step["id"])
            amend_info = f" (amended {step['amend_count']}x)" if step["amend_count"] else ""
            cost_info = f" ${step['cost_usd']:.2f}" if step.get("cost_usd") else ""
            click.echo(f"  {icon} Step {step['step']}: {title}  [{step['status']}{amend_info}{cost_info}]")

        # Summary
        approved = sum(1 for s in steps if s["status"] == "approved")
        click.echo(f"\n  Progress: {approved}/{len(steps)} steps approved")
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

    # Reset amend counts and retry failed explorations
    state.update_plan(conn, plan_id, status="active")
    conn.close()

    from . import gate  # late import to avoid circular
    for exp in failed:
        click.echo(f"Retrying: {exp['id']}")
        try:
            gate.retry_exploration(
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                exploration_id=exp["id"],
            )
        except RuntimeError as e:
            click.echo(f"  Retry failed: {e}", err=True)

    click.echo(f"Plan '{plan_id}' resumed. {len(failed)} step(s) retried.")
