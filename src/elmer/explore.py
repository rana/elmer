"""Exploration orchestration — create worktree, assemble prompt, spawn worker."""

import re
from pathlib import Path

from . import config, state, worker, worktree


def slugify(text: str, max_length: int = 60) -> str:
    """Convert topic text to a URL/branch-safe slug."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit("-", 1)[0]
    return slug


def _make_unique_slug(conn, base_slug: str) -> str:
    """Append a counter if the slug already exists."""
    if state.get_exploration(conn, base_slug) is None:
        return base_slug
    counter = 2
    while state.get_exploration(conn, f"{base_slug}-{counter}") is not None:
        counter += 1
    return f"{base_slug}-{counter}"


def _assemble_prompt(archetype_path: Path, topic: str) -> str:
    """Load archetype template and substitute $TOPIC."""
    template = archetype_path.read_text()
    return template.replace("$TOPIC", topic)


def start_exploration(
    *,
    topic: str,
    archetype: str,
    model: str,
    max_turns: int,
    elmer_dir: Path,
    project_dir: Path,
) -> str:
    """Start a new exploration. Returns the exploration slug."""
    if not worker.check_claude_available():
        raise RuntimeError(
            "claude CLI not found in PATH. Install Claude Code first."
        )

    # Resolve archetype template
    archetype_path = config.resolve_archetype(elmer_dir, archetype)

    # Generate unique slug
    conn = state.get_db(elmer_dir)
    base_slug = slugify(topic)
    if not base_slug:
        base_slug = "exploration"
    slug = _make_unique_slug(conn, base_slug)

    branch = f"elmer/{slug}"
    worktree_path = elmer_dir / "worktrees" / slug
    log_path = elmer_dir / "logs" / f"{slug}.log"

    # Check branch doesn't already exist
    if worktree.branch_exists(project_dir, branch):
        raise RuntimeError(
            f"Branch '{branch}' already exists. "
            f"Use 'elmer clean' or 'elmer reject {slug}' first."
        )

    # Assemble prompt
    prompt = _assemble_prompt(archetype_path, topic)

    # Create worktree
    worktree.create_worktree(project_dir, branch, worktree_path)

    # Spawn claude session
    pid = worker.spawn_claude(
        prompt=prompt,
        cwd=worktree_path,
        model=model,
        log_path=log_path,
        max_turns=max_turns,
    )

    # Record state
    state.create_exploration(
        conn,
        id=slug,
        topic=topic,
        archetype=archetype,
        branch=branch,
        worktree_path=str(worktree_path),
        model=model,
        pid=pid,
    )
    conn.close()

    return slug
