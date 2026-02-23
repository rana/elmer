"""AI archetype selection — pick the best archetype for a topic."""

from pathlib import Path

from . import config, worker
from .worker import ClaudeResult

# Archetypes that are meta-prompts (not exploration archetypes).
# These should never be selected by the AI for exploration use.
META_ARCHETYPES = frozenset({
    "generate-topics",
    "prompt-gen",
    "review-gate",
    "select-archetype",
})


def list_exploration_archetypes(elmer_dir: Path) -> dict[str, str]:
    """List available exploration archetypes with their first-line descriptions.

    Returns {name: description} for archetypes that are valid exploration targets.
    Checks project-local archetypes first, then bundled. Meta-archetypes are excluded.
    """
    archetypes: dict[str, str] = {}

    # Bundled archetypes
    for path in sorted(config.ARCHETYPES_DIR.glob("*.md")):
        name = path.stem
        if name not in META_ARCHETYPES:
            archetypes[name] = path.read_text().split("\n", 1)[0].strip()

    # Project-local archetypes (override bundled descriptions)
    local_dir = elmer_dir / "archetypes"
    if local_dir.exists():
        for path in sorted(local_dir.glob("*.md")):
            name = path.stem
            if name not in META_ARCHETYPES:
                archetypes[name] = path.read_text().split("\n", 1)[0].strip()

    return archetypes


def select_archetype(
    *,
    topic: str,
    elmer_dir: Path,
    project_dir: Path,
    model: str = "sonnet",
    max_turns: int = 3,
) -> tuple[str, ClaudeResult]:
    """Use AI to pick the best archetype for a topic.

    Returns (archetype_name, claude_result) tuple.
    Falls back to config default if AI output doesn't match a known archetype.
    """
    available = list_exploration_archetypes(elmer_dir)

    # Format archetype list for the meta-prompt
    archetype_list = "\n".join(
        f"- **{name}**: {desc}" for name, desc in sorted(available.items())
    )

    # Try agent-aware invocation, fall back to template substitution
    agent_config = config.resolve_meta_agent(project_dir, "select-archetype")

    if agent_config is not None:
        meta_prompt = (
            f"## Topic\n\n{topic}\n\n"
            f"## Available Archetypes\n\n{archetype_list}"
        )
    else:
        meta_path = config.resolve_archetype(elmer_dir, "select-archetype")
        meta_template = meta_path.read_text()
        meta_prompt = (
            meta_template
            .replace("$TOPIC", topic)
            .replace("$ARCHETYPES", archetype_list)
        )

    result = worker.run_claude(
        prompt=meta_prompt,
        cwd=project_dir,
        model=model,
        max_turns=max_turns,
        agent_config=agent_config,
    )

    # Parse the output — should be a single archetype name
    selected = result.output.strip().lower().replace(" ", "-")

    # Validate against known archetypes
    if selected not in available:
        # Try partial match (AI might include .md or extra text)
        for name in available:
            if name in selected:
                selected = name
                break
        else:
            # Fall back to config default
            cfg = config.load_config(elmer_dir)
            selected = cfg.get("defaults", {}).get("archetype", "explore-act")

    return selected, result
