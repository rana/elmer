"""Milestone decomposition — convert milestones into implementation plans.

Handles the planning phase: reading project context, calling the decompose
meta-agent, parsing plan JSON, validating structure and prerequisites,
and detecting parallel conflicts. Produces plan dicts consumed by
execute_plan() in implement.py.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

import click

from . import config, state, worker


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


def _read_exploration_proposal(
    elmer_dir: Path,
    exploration_id: str,
) -> str:
    """Read an exploration's PROPOSAL.md for feeding into decomposition (A4).

    Checks the worktree first, falls back to archive. Returns the content
    or raises RuntimeError if neither exists.
    """
    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)
    conn.close()

    # Try worktree (active exploration)
    if exp is not None:
        wt_path = Path(exp["worktree_path"])
        proposal_path = wt_path / "PROPOSAL.md"
        if proposal_path.exists():
            return proposal_path.read_text()

    # Try archive (approved/declined exploration)
    proposals_dir = elmer_dir / "proposals"
    if proposals_dir.exists():
        # Try direct ID match
        archive_path = proposals_dir / f"{exploration_id}.md"
        if archive_path.exists():
            return archive_path.read_text()
        # Scan for topic-derived filename
        for p in proposals_dir.glob("*.md"):
            if exploration_id in p.stem:
                return p.read_text()

    raise RuntimeError(
        f"No PROPOSAL.md found for exploration '{exploration_id}'. "
        f"Checked worktree and archive."
    )


def decompose_milestone(
    *,
    milestone_ref: str,
    elmer_dir: Path,
    project_dir: Path,
    model: Optional[str] = None,
    max_turns: int = 30,
    from_exploration: Optional[str] = None,
) -> dict:
    """Decompose a milestone into implementation steps.

    Calls the decompose meta-agent with project context.
    Returns a plan dict with 'steps', 'questions', and 'milestone' keys.

    If from_exploration is provided (A4), the exploration's PROPOSAL.md is
    fed directly to the decompose agent as structured context, producing
    higher-fidelity plans that inherit the exploration's analysis.
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

    # Inject exploration proposal as additional context (A4)
    if from_exploration:
        try:
            proposal_text = _read_exploration_proposal(elmer_dir, from_exploration)
            # Truncate very large proposals
            if len(proposal_text) > 15000:
                proposal_text = proposal_text[:15000] + "\n\n[...truncated...]"
            prompt = (
                f"{prompt}\n\n"
                f"## Source Exploration Proposal\n\n"
                f"The following proposal from exploration '{from_exploration}' "
                f"contains the detailed analysis and action items that should inform "
                f"your decomposition. Use its findings, file targets, and ordering "
                f"as a primary input — don't re-derive what it already analyzed:\n\n"
                f"{proposal_text}"
            )
        except RuntimeError as e:
            click.echo(f"Warning: could not read exploration proposal: {e}", err=True)

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


def inject_answers(plan: dict, answers: dict[int, str]) -> dict:
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


def validate_plan(
    plan: dict,
    project_dir: Path,
) -> list[str]:
    """Validate plan structure and coherence before execution.

    Checks agent definitions exist, dependencies form a valid DAG, step
    indices are within range, and steps have required fields. Returns list
    of errors.
    """
    errors: list[str] = []
    steps = plan.get("steps", [])

    if not steps:
        errors.append("plan has no steps")
        return errors

    num_steps = len(steps)

    for i, step in enumerate(steps):
        # Required field: topic
        if not step.get("topic"):
            errors.append(f"step {i}: missing 'topic' field")

        # Validate agent exists for archetype
        archetype = step.get("archetype", "implement")
        if config.resolve_agent(project_dir, archetype) is None:
            errors.append(f"step {i}: no agent definition for archetype '{archetype}'")

        # Validate dependency indices
        deps = step.get("depends_on", [])
        for dep_idx in deps:
            if not isinstance(dep_idx, int):
                errors.append(f"step {i}: dependency '{dep_idx}' is not an integer")
            elif dep_idx < 0 or dep_idx >= num_steps:
                errors.append(f"step {i}: dependency index {dep_idx} out of range (0-{num_steps - 1})")
            elif dep_idx >= i:
                errors.append(f"step {i}: depends on step {dep_idx} (forward/self dependency)")

    # Check for cycles in dependency graph
    adj: dict[int, list[int]] = {i: step.get("depends_on", []) for i, step in enumerate(steps)}
    visited: set[int] = set()
    in_stack: set[int] = set()

    def _has_cycle(node: int) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for dep in adj.get(node, []):
            if isinstance(dep, int) and 0 <= dep < num_steps:
                if _has_cycle(dep):
                    return True
        in_stack.discard(node)
        return False

    for i in range(num_steps):
        if _has_cycle(i):
            errors.append(f"dependency cycle detected involving step {i}")
            break

    return errors


def validate_step_metadata(plan: dict) -> list[str]:
    """Validate step metadata completeness. Returns list of warnings.

    Checks for missing verify_cmd, empty relevant_docs, and requires_env
    referencing vars that aren't in plan-level prerequisites. These are
    warnings (not errors) — plans execute without them, but quality improves
    with complete metadata.
    """
    warnings: list[str] = []
    steps = plan.get("steps", [])
    plan_env_vars = set(plan.get("prerequisites", {}).get("env_vars", []))

    for i, step in enumerate(steps):
        # Missing verify_cmd
        if not step.get("verify_cmd"):
            warnings.append(f"step {i}: no verify_cmd — verification will be skipped")

        # Missing relevant_docs
        if not step.get("relevant_docs"):
            warnings.append(f"step {i}: no relevant_docs — worker will read docs unguided")

        # requires_env vars not in plan-level prerequisites
        requires_env = step.get("requires_env", [])
        for var in requires_env:
            if var not in plan_env_vars:
                warnings.append(
                    f"step {i}: requires_env '{var}' not in plan prerequisites.env_vars"
                )

    return warnings


def estimate_plan_duration(plan: dict) -> tuple[float | None, list[str]]:
    """Estimate total plan duration from step estimated_seconds fields.

    Returns (total_seconds, warnings) where total_seconds is the sum of all
    estimated_seconds values, or None if no steps provide estimates.
    Warnings include missing-estimate notices and max-hours violations.
    """
    steps = plan.get("steps", [])
    warnings: list[str] = []

    estimates = []
    for i, step in enumerate(steps):
        est = step.get("estimated_seconds")
        if est is not None:
            if isinstance(est, (int, float)) and est >= 0:
                estimates.append(est)
            else:
                warnings.append(f"step {i}: invalid estimated_seconds ({est!r})")

    if not estimates:
        return None, warnings

    total = sum(estimates)
    if len(estimates) < len(steps):
        missing = len(steps) - len(estimates)
        warnings.append(f"{missing}/{len(steps)} steps have no duration estimate")

    return total, warnings


def detect_parallel_conflicts(plan: dict) -> list[str]:
    """Detect potential file conflicts between parallel plan steps.

    Analyzes key_files declarations to find steps that could run in parallel
    (no dependency chain between them) but declare overlapping files.
    Returns list of warning strings.
    """
    steps = plan.get("steps", [])
    if not steps:
        return []

    warnings: list[str] = []

    # Build dependency closure: for each step, which steps must complete first?
    num_steps = len(steps)
    transitive_deps: dict[int, set[int]] = {i: set() for i in range(num_steps)}
    for i, step in enumerate(steps):
        direct = set(step.get("depends_on", []))
        queue = list(direct)
        visited: set[int] = set()
        while queue:
            dep = queue.pop(0)
            if dep in visited or dep < 0 or dep >= num_steps:
                continue
            visited.add(dep)
            queue.extend(steps[dep].get("depends_on", []))
        transitive_deps[i] = visited

    # Find pairs of steps that could run in parallel
    for i in range(num_steps):
        for j in range(i + 1, num_steps):
            if j in transitive_deps[i] or i in transitive_deps[j]:
                continue  # Sequential

            files_i = set(steps[i].get("key_files", []))
            files_j = set(steps[j].get("key_files", []))
            overlap = files_i & files_j
            if overlap:
                warnings.append(
                    f"steps {i} and {j} may conflict: both declare key_files {', '.join(sorted(overlap))}"
                )

    return warnings
