"""Topic generation — AI proposes research topics from project context."""

import re
from pathlib import Path
from typing import Optional

from . import config, state, worker


def generate_topics(
    *,
    elmer_dir: Path,
    project_dir: Path,
    count: int = 5,
    follow_up_id: Optional[str] = None,
    model: str = "sonnet",
    max_turns: int = 5,
) -> list[str]:
    """Generate research topics using claude. Returns list of topic strings."""
    if not worker.check_claude_available():
        raise RuntimeError(
            "claude CLI not found in PATH. Install Claude Code first."
        )

    # Build context sections
    conn = state.get_db(elmer_dir)
    history = _format_history(state.list_explorations(conn))
    followup_context = ""

    if follow_up_id:
        followup_context = _build_followup_context(conn, follow_up_id)

    conn.close()

    # Try agent-aware invocation, fall back to template substitution
    agent_config = config.resolve_meta_agent(project_dir, "generate-topics")

    if agent_config is not None:
        prompt = (
            f"Generate exactly {count} research topics.\n\n"
            f"## Exploration History\n\n"
            f"{history or '(none yet)'}\n\n"
            f"{followup_context}"
        ).strip()
    else:
        template_path = config.resolve_archetype(elmer_dir, "generate-topics")
        template = template_path.read_text()
        prompt = (
            template
            .replace("$COUNT", str(count))
            .replace("$HISTORY", history or "(none yet)")
            .replace("$FOLLOWUP_CONTEXT", followup_context)
        )

    # Run claude synchronously
    result = worker.run_claude(
        prompt=prompt,
        cwd=project_dir,
        model=model,
        max_turns=max_turns,
        agent_config=agent_config,
    )

    # Record meta-operation cost
    conn = state.get_db(elmer_dir)
    state.record_meta_cost(
        conn,
        operation="generate",
        model=model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
    )
    conn.close()

    topics = _parse_topics(result.output)
    if not topics:
        raise RuntimeError(
            f"Failed to parse topics from claude output:\n{result.output}"
        )

    return topics[:count]


def _format_history(explorations: list) -> str:
    """Format exploration history for the prompt."""
    if not explorations:
        return ""

    lines = []
    for exp in explorations:
        status = exp["status"]
        topic = exp["topic"]
        lines.append(f"- [{status}] {topic}")

    return "\n".join(lines)


def _build_followup_context(conn, follow_up_id: str) -> str:
    """Build follow-up context from a completed exploration."""
    exp = state.get_exploration(conn, follow_up_id)
    if exp is None:
        raise RuntimeError(f"Exploration '{follow_up_id}' not found.")

    if exp["status"] not in ("done", "approved"):
        raise RuntimeError(
            f"Exploration '{follow_up_id}' has status '{exp['status']}'. "
            f"Follow-up requires a completed exploration (done or approved)."
        )

    # Read the proposal
    worktree_path = Path(exp["worktree_path"])
    proposal_path = worktree_path / "PROPOSAL.md"

    proposal_text = ""
    if proposal_path.exists():
        proposal_text = proposal_path.read_text()
    else:
        proposal_text = "(no proposal file found)"

    return (
        f"## Follow-Up Context\n\n"
        f"Generate follow-up topics based on this completed exploration:\n\n"
        f"**Parent topic:** {exp['topic']}\n\n"
        f"### Proposal\n\n"
        f"{proposal_text}"
    )


def _parse_topics(output: str) -> list[str]:
    """Extract topics from a numbered list in claude's output."""
    topics = []
    for line in output.splitlines():
        match = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if match:
            topic = match.group(1).strip()
            if topic:
                topics.append(topic)
    return topics
