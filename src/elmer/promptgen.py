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

    # Load the meta-prompt template
    meta_path = config.resolve_archetype(elmer_dir, "prompt-gen")
    meta_template = meta_path.read_text()

    # Assemble the meta-prompt
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
    )

    return result.output, result
