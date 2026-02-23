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
    # Load the archetype template as a hint
    archetype_path = config.resolve_archetype(elmer_dir, archetype)
    archetype_hint = archetype_path.read_text()

    # Try agent-aware invocation, fall back to template substitution
    agent_config = config.resolve_meta_agent(project_dir, "prompt-gen")

    if agent_config is not None:
        meta_prompt = (
            f"## Topic to Explore\n\n{topic}\n\n"
            f"## Archetype Hint\n\n"
            f"The user selected the \"{archetype}\" archetype. "
            f"Here is its template for reference:\n\n"
            f"```\n{archetype_hint}\n```"
        )
    else:
        meta_path = config.resolve_archetype(elmer_dir, "prompt-gen")
        meta_template = meta_path.read_text()
        meta_prompt = (
            meta_template
            .replace("$TOPIC", topic)
            .replace("$ARCHETYPE_NAME", archetype)
            .replace("$ARCHETYPE_HINT", archetype_hint)
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
