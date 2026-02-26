"""Skill hooks — invoke project-defined Claude Code skills at lifecycle points.

Skills are markdown files in .claude/skills/<name>/SKILL.md. They are invoked
via claude -p with the proposal text injected as context. Each hook returns
a pass/fail verdict that can gate the lifecycle transition (ADR-064).

Lifecycle events:
  - on_done: after PROPOSAL.md is committed but before verification
  - pre_approve: after verification passes, before auto-approve gate
  - post_approve: after merge (informational, cannot block)
"""

import logging
import re
from pathlib import Path
from typing import Optional

from . import config, state, worker

logger = logging.getLogger("elmer.hooks")


def run_skill_hook(
    *,
    skill_name: str,
    event: str,
    proposal_text: str,
    exploration_id: str,
    elmer_dir: Path,
    project_dir: Path,
    arguments: str = "",
) -> tuple[bool, str]:
    """Run a single skill hook. Returns (passed, output).

    The skill body is loaded from .claude/skills/<name>/SKILL.md.
    $ARGUMENTS in the skill body is substituted with the arguments parameter.
    The proposal text is appended as context.

    For on_done and pre_approve events, the skill must output a verdict line:
        VERDICT: PASS — <reason>
        VERDICT: FAIL — <reason>

    If no verdict line is found, the hook is treated as passing (informational).
    For post_approve events, the result is always informational.
    """
    skill = config.resolve_skill(project_dir, skill_name)
    if skill is None:
        logger.warning("Skill '%s' not found in project, skipping hook", skill_name)
        return True, f"(skill '{skill_name}' not found)"

    cfg = config.load_config(elmer_dir)
    hooks_cfg = cfg.get("hooks", {})
    model = hooks_cfg.get("model", "sonnet")
    max_turns = hooks_cfg.get("max_turns", 10)

    # Build prompt: skill body + proposal context
    skill_body = skill["prompt"]
    if arguments:
        skill_body = skill_body.replace("$ARGUMENTS", arguments)
    else:
        skill_body = skill_body.replace("$ARGUMENTS", "(full proposal)")

    prompt = (
        f"## Skill Hook: {skill_name} ({event})\n\n"
        f"{skill_body}\n\n"
        f"## Proposal Under Review\n\n"
        f"Exploration: {exploration_id}\n\n"
        f"{proposal_text}\n\n"
        f"## Required Output\n\n"
        f"After your analysis, output a verdict line:\n"
        f"VERDICT: PASS — <brief reason>\n"
        f"or\n"
        f"VERDICT: FAIL — <brief reason why this should not proceed>"
    )

    try:
        result = worker.run_claude(
            prompt=prompt,
            cwd=project_dir,
            model=model,
            max_turns=max_turns,
        )
    except RuntimeError as e:
        logger.warning("Skill hook '%s' failed to run: %s", skill_name, e)
        return True, f"(hook execution error: {e})"

    # Record cost
    conn = state.get_db(elmer_dir)
    state.record_meta_cost(
        conn,
        operation=f"hook_{event}_{skill_name}",
        model=model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        exploration_id=exploration_id,
    )
    conn.close()

    # Parse verdict
    output = result.output or ""
    passed, reason = _parse_hook_verdict(output)

    # post_approve hooks are always informational
    if event == "post_approve":
        return True, output

    return passed, reason or output[:300]


def run_event_hooks(
    *,
    event: str,
    proposal_text: str,
    exploration_id: str,
    elmer_dir: Path,
    project_dir: Path,
    notify: Optional[callable] = None,
) -> tuple[bool, list[tuple[str, bool, str]]]:
    """Run all skill hooks for a lifecycle event.

    Returns (all_passed, results) where results is a list of
    (skill_name, passed, output) tuples.
    """
    if notify is None:
        notify = logger.info

    hook_skills = config.get_hook_skills(elmer_dir)
    skills = hook_skills.get(event, [])
    if not skills:
        return True, []

    results: list[tuple[str, bool, str]] = []
    all_passed = True

    for skill_name in skills:
        notify(f"  Running {event} hook: {skill_name}")
        passed, output = run_skill_hook(
            skill_name=skill_name,
            event=event,
            proposal_text=proposal_text,
            exploration_id=exploration_id,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
        )
        results.append((skill_name, passed, output))
        if passed:
            notify(f"    {skill_name}: PASS")
        else:
            notify(f"    {skill_name}: FAIL — {output[:100]}")
            all_passed = False

    return all_passed, results


def _parse_hook_verdict(output: str) -> tuple[bool, str]:
    """Parse VERDICT line from hook output. Returns (passed, reason).

    If no verdict line is found, defaults to pass (informational hook).
    """
    for line in output.splitlines():
        match = re.match(
            r"^\s*VERDICT:\s*(PASS|FAIL)\s*(?:—|-+)\s*(.*)$",
            line,
            re.IGNORECASE,
        )
        if match:
            verdict = match.group(1).upper()
            reason = match.group(2).strip()
            return verdict == "PASS", reason

    # No verdict line — treat as informational (pass)
    return True, ""
