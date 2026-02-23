"""Auto-approve gate — AI evaluates proposals against configurable criteria."""

import re
from pathlib import Path

from . import config, gate, state, worker, worktree


def evaluate(
    elmer_dir: Path,
    project_dir: Path,
    exploration_id: str,
) -> bool:
    """Evaluate a proposal for auto-approval. Returns True if approved."""
    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)
    conn.close()

    if exp is None or exp["status"] != "done":
        return False

    # Load config
    cfg = config.load_config(elmer_dir)
    aa_cfg = cfg.get("auto_approve", {})
    model = aa_cfg.get("model", "sonnet")
    max_turns = aa_cfg.get("max_turns", 3)
    criteria = aa_cfg.get("criteria", "document-only proposals with no code changes")
    max_files = aa_cfg.get("max_files_changed", 10)
    require_proposal = aa_cfg.get("require_proposal", True)

    # Read proposal
    worktree_path = Path(exp["worktree_path"])
    proposal_path = worktree_path / "PROPOSAL.md"

    if require_proposal and not proposal_path.exists():
        return False

    proposal_text = proposal_path.read_text() if proposal_path.exists() else "(no proposal)"

    # Get diff stat
    diff = worktree.get_branch_diff(project_dir, exp["branch"])

    # Quick check: if too many files changed, skip AI review
    file_count = _count_files_in_diff(diff)
    if file_count > max_files:
        return False

    # Try agent-aware invocation, fall back to template substitution
    agent_config = config.resolve_meta_agent(project_dir, "review-gate")

    if agent_config is not None:
        prompt = (
            f"## Approval Criteria\n\n{criteria}\n\n"
            f"## Proposal\n\n{proposal_text}\n\n"
            f"## Files Changed\n\n{diff or '(no changes)'}"
        )
    else:
        template_path = config.resolve_archetype(elmer_dir, "review-gate")
        template = template_path.read_text()
        prompt = (
            template
            .replace("$PROPOSAL", proposal_text)
            .replace("$DIFF", diff or "(no changes)")
            .replace("$CRITERIA", criteria)
        )

    # Run AI review
    try:
        result = worker.run_claude(
            prompt=prompt,
            cwd=project_dir,
            model=model,
            max_turns=max_turns,
            agent_config=agent_config,
        )
    except RuntimeError:
        return False  # Review failed, leave for human

    # Record meta-operation cost
    conn = state.get_db(elmer_dir)
    state.record_meta_cost(
        conn,
        operation="auto_approve",
        model=model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        exploration_id=exploration_id,
    )

    verdict, reason = _parse_verdict(result.output)

    if verdict == "approve":
        conn.close()
        gate.approve_exploration(elmer_dir, project_dir, exploration_id)
        return True

    # Rejected or unparseable — leave for human review, store reason
    if reason:
        current = state.get_exploration(conn, exploration_id)
        summary = current["proposal_summary"] or ""
        state.update_exploration(
            conn, exploration_id,
            proposal_summary=f"{summary} [auto-review: {reason}]"
        )

    conn.close()
    return False


def _parse_verdict(output: str) -> tuple[str, str]:
    """Parse VERDICT line from reviewer output. Returns (verdict, reason)."""
    for line in output.splitlines():
        match = re.match(
            r"^\s*VERDICT:\s*(APPROVE|REJECT)\s*(?:—|-+)\s*(.*)$",
            line,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).lower(), match.group(2).strip()
    return "reject", "could not parse reviewer verdict"


def _count_files_in_diff(diff: str) -> int:
    """Count files in a git diff --stat output."""
    if not diff:
        return 0
    # Last line of diff --stat is the summary, count lines before it
    lines = [l for l in diff.strip().splitlines() if "|" in l]
    return len(lines)
