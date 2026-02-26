"""Two-stage prompt generation — AI generates the exploration prompt."""

from pathlib import Path

from . import config, worker
from .worker import ClaudeResult


def generate_prompt(
    *,
    topic: str,
    archetype: str,
    elmer_dir: Path,
    project_dir: Path,
    model: str = "sonnet",
    max_turns: int = 3,
) -> tuple[str, ClaudeResult]:
    """Generate an exploration prompt using AI (Stage 1).

    Reads project docs and the archetype template, then asks Claude
    to generate an optimal exploration prompt for the given topic.
    Returns (generated_prompt, claude_result) tuple.
    """
    # Load the archetype's agent definition as a methodology hint
    archetype_agent = config.resolve_agent(project_dir, archetype)
    archetype_hint = archetype_agent["prompt"] if archetype_agent else f"(no agent definition for '{archetype}')"

    agent_config = config.resolve_meta_agent(project_dir, "prompt-gen")

    meta_prompt = (
        f"## Topic to Explore\n\n{topic}\n\n"
        f"## Archetype Hint\n\n"
        f"The user selected the \"{archetype}\" archetype. "
        f"Here is its methodology for reference:\n\n"
        f"```\n{archetype_hint}\n```"
    )

    # Run Stage 1 synchronously — Claude reads project docs and generates the prompt
    result = worker.run_claude(
        prompt=meta_prompt,
        cwd=project_dir,
        model=model,
        max_turns=max_turns,
        agent_config=agent_config,
    )

    return result.output, result
