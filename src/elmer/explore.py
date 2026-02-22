"""Exploration orchestration — create worktree, assemble prompt, spawn worker."""

import re
from pathlib import Path
from typing import Optional

from . import archselect, config, insights, promptgen, state, worker, worktree


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


def _assemble_prompt(
    archetype_path: Path,
    topic: str,
    elmer_dir: Optional[Path] = None,
    project_dir: Optional[Path] = None,
) -> str:
    """Load archetype template, substitute $TOPIC, inject cross-project insights."""
    template = archetype_path.read_text()
    prompt = template.replace("$TOPIC", topic)

    # Inject cross-project insights if enabled
    if elmer_dir is not None:
        try:
            cfg = config.load_config(elmer_dir)
            ins_cfg = cfg.get("insights", {})
            if ins_cfg.get("inject", True) and ins_cfg.get("enabled", False):
                project_name = project_dir.name if project_dir else None
                relevant = insights.get_relevant_insights(
                    topic,
                    project_name=project_name,
                    limit=ins_cfg.get("inject_limit", 5),
                )
                context = insights.format_insights_context(relevant)
                if context:
                    prompt = prompt + "\n\n" + context
        except Exception:
            pass  # Best-effort — never block exploration for insight injection

    return prompt


def start_exploration(
    *,
    topic: str,
    archetype: str,
    model: str,
    max_turns: int,
    elmer_dir: Path,
    project_dir: Path,
    parent_id: Optional[str] = None,
    depends_on: Optional[list[str]] = None,
    auto_approve: bool = False,
    generate_prompt: bool = False,
    auto_archetype: bool = False,
    budget_usd: Optional[float] = None,
    on_approve: Optional[str] = None,
    on_reject: Optional[str] = None,
) -> tuple[str, str]:
    """Start a new exploration. Returns (slug, archetype_used).

    If auto_archetype is True, AI selects the best archetype for the topic
    before the exploration starts. The selection cost is tracked.

    If depends_on contains IDs of explorations that aren't yet approved,
    the exploration is created in 'pending' status and launched later
    by schedule_ready().

    If generate_prompt is True, uses two-stage prompt generation: AI generates
    the exploration prompt (Stage 1) before spawning the worker (Stage 2).

    If budget_usd is set, passes --max-budget-usd to the claude session.

    on_approve/on_reject are shell commands executed after approval/rejection.
    $ID and $TOPIC are substituted with the exploration ID and topic.
    """
    if not worker.check_claude_available():
        raise RuntimeError(
            "claude CLI not found in PATH. Install Claude Code first."
        )

    conn = state.get_db(elmer_dir)

    # AI archetype selection (before anything else, so pending explorations
    # store the selected archetype, not the placeholder default)
    if auto_archetype:
        cfg = config.load_config(elmer_dir)
        sel_cfg = cfg.get("archetype_selection", {})
        sel_model = sel_cfg.get("model", "sonnet")
        sel_max_turns = sel_cfg.get("max_turns", 3)

        archetype, sel_result = archselect.select_archetype(
            topic=topic,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=sel_model,
            max_turns=sel_max_turns,
        )
        # Cost tracking uses a temp slug — we'll update exploration_id after insert
        state.record_meta_cost(
            conn,
            operation="archetype_select",
            model=sel_model,
            input_tokens=sel_result.input_tokens,
            output_tokens=sel_result.output_tokens,
            cost_usd=sel_result.cost_usd,
        )

    # Resolve archetype template (validate it exists even if deferred)
    archetype_path = config.resolve_archetype(elmer_dir, archetype)

    # Generate unique slug
    base_slug = slugify(topic)
    if not base_slug:
        base_slug = "exploration"
    slug = _make_unique_slug(conn, base_slug)

    branch = f"elmer/{slug}"
    worktree_path = elmer_dir / "worktrees" / slug
    log_path = elmer_dir / "logs" / f"{slug}.log"

    # Validate dependencies exist
    if depends_on:
        for dep_id in depends_on:
            if state.get_exploration(conn, dep_id) is None:
                conn.close()
                raise RuntimeError(f"Dependency '{dep_id}' not found.")

    # Check if blocked by unmet dependencies
    blocked = False
    if depends_on:
        for dep_id in depends_on:
            dep = state.get_exploration(conn, dep_id)
            if dep["status"] != "approved":
                blocked = True
                break

    if blocked:
        # Create as pending — no worktree, no worker
        state.create_exploration(
            conn,
            id=slug,
            topic=topic,
            archetype=archetype,
            branch=branch,
            worktree_path=str(worktree_path),
            model=model,
            pid=None,
            status="pending",
            parent_id=parent_id,
            max_turns=max_turns,
            auto_approve=auto_approve,
            generate_prompt=generate_prompt,
            budget_usd=budget_usd,
            on_approve=on_approve,
            on_reject=on_reject,
        )
        for dep_id in depends_on:
            state.add_dependency(conn, slug, dep_id)
        conn.close()
        return slug, archetype

    # Not blocked — start immediately
    if worktree.branch_exists(project_dir, branch):
        conn.close()
        raise RuntimeError(
            f"Branch '{branch}' already exists. "
            f"Use 'elmer clean' or 'elmer reject {slug}' first."
        )

    if generate_prompt:
        prompt, gen_result = promptgen.generate_prompt(
            topic=topic,
            archetype=archetype,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
        )
        # Record prompt generation cost (linked to this exploration after insert)
        state.record_meta_cost(
            conn,
            operation="prompt_gen",
            model=model,
            input_tokens=gen_result.input_tokens,
            output_tokens=gen_result.output_tokens,
            cost_usd=gen_result.cost_usd,
            exploration_id=slug,
        )
    else:
        prompt = _assemble_prompt(archetype_path, topic, elmer_dir, project_dir)
    worktree.create_worktree(project_dir, branch, worktree_path)

    pid = worker.spawn_claude(
        prompt=prompt,
        cwd=worktree_path,
        model=model,
        log_path=log_path,
        max_turns=max_turns,
        budget_usd=budget_usd,
    )

    state.create_exploration(
        conn,
        id=slug,
        topic=topic,
        archetype=archetype,
        branch=branch,
        worktree_path=str(worktree_path),
        model=model,
        pid=pid,
        parent_id=parent_id,
        max_turns=max_turns,
        auto_approve=auto_approve,
        generate_prompt=generate_prompt,
        budget_usd=budget_usd,
        on_approve=on_approve,
        on_reject=on_reject,
    )

    # Record dependencies even if all satisfied (for lineage tracking)
    if depends_on:
        for dep_id in depends_on:
            state.add_dependency(conn, slug, dep_id)

    conn.close()
    return slug, archetype


def launch_pending(
    *,
    exploration_id: str,
    elmer_dir: Path,
    project_dir: Path,
) -> None:
    """Launch a pending exploration that's now unblocked."""
    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)

    if exp is None or exp["status"] != "pending":
        conn.close()
        return

    archetype = exp["archetype"]
    model = exp["model"]
    max_turns = exp["max_turns"] or 50
    topic = exp["topic"]
    branch = exp["branch"]
    worktree_path = Path(exp["worktree_path"])
    log_path = elmer_dir / "logs" / f"{exploration_id}.log"
    budget_usd = exp["budget_usd"]

    use_generate = bool(exp["generate_prompt"])

    if use_generate:
        try:
            prompt, gen_result = promptgen.generate_prompt(
                topic=topic,
                archetype=archetype,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
            )
            state.record_meta_cost(
                conn,
                operation="prompt_gen",
                model=model,
                input_tokens=gen_result.input_tokens,
                output_tokens=gen_result.output_tokens,
                cost_usd=gen_result.cost_usd,
                exploration_id=exploration_id,
            )
        except RuntimeError:
            # Fall back to static template if prompt generation fails
            archetype_path = config.resolve_archetype(elmer_dir, archetype)
            prompt = _assemble_prompt(archetype_path, topic, elmer_dir, project_dir)
    else:
        archetype_path = config.resolve_archetype(elmer_dir, archetype)
        prompt = _assemble_prompt(archetype_path, topic, elmer_dir, project_dir)

    if worktree.branch_exists(project_dir, branch):
        state.update_exploration(conn, exploration_id, status="failed",
                                 proposal_summary="(branch conflict on deferred start)")
        conn.close()
        return

    worktree.create_worktree(project_dir, branch, worktree_path)

    pid = worker.spawn_claude(
        prompt=prompt,
        cwd=worktree_path,
        model=model,
        log_path=log_path,
        max_turns=max_turns,
        budget_usd=budget_usd,
    )

    state.update_exploration(conn, exploration_id, status="running", pid=pid)
    conn.close()


def schedule_ready(elmer_dir: Path, project_dir: Path) -> list[str]:
    """Find pending explorations with all dependencies met and launch them."""
    conn = state.get_db(elmer_dir)
    ready = state.get_pending_ready(conn)
    conn.close()

    launched = []
    for exp in ready:
        launch_pending(
            exploration_id=exp["id"],
            elmer_dir=elmer_dir,
            project_dir=project_dir,
        )
        launched.append(exp["id"])

    return launched
