"""Exploration orchestration — create worktree, assemble prompt, spawn worker."""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import archselect, config, digest as digest_mod, insights, promptgen, state, worker, worktree


def slugify(text: str, max_length: int = 40) -> str:
    """Convert topic text to a URL/branch-safe slug."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit("-", 1)[0]
    return slug


def _make_unique_slug(conn, base_slug: str, elmer_dir: Path) -> str:
    """Append a counter if the slug already exists in DB or logs.

    Checks both the active database and the logs directory.
    After clean deletes DB records, logs persist — without this check,
    a reused slug would overwrite them (ADR-032). Proposal archives use
    topic-derived filenames (ADR-036) so are not checked here.
    """
    def _slug_exists(slug: str) -> bool:
        if state.get_exploration(conn, slug) is not None:
            return True
        if (elmer_dir / "logs" / f"{slug}.log").exists():
            return True
        return False

    if not _slug_exists(base_slug):
        return base_slug
    counter = 2
    while _slug_exists(f"{base_slug}-{counter}"):
        counter += 1
    return f"{base_slug}-{counter}"



def _inject_insights(
    prompt: str,
    topic: str,
    elmer_dir: Optional[Path] = None,
    project_dir: Optional[Path] = None,
) -> str:
    """Append cross-project insights to a prompt if enabled."""
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


def _inject_digest(
    prompt: str,
    elmer_dir: Path,
) -> str:
    """Append the latest convergence digest to a prompt if enabled (G1).

    Injects truncated digest (~4K chars) so workers benefit from accumulated
    cross-exploration understanding rather than re-discovering known insights.
    """
    try:
        cfg = config.load_config(elmer_dir)
        digest_cfg = cfg.get("digest", {})
        if not digest_cfg.get("inject_into_explorations", True):
            return prompt
        content = digest_mod.get_latest_digest(elmer_dir)
        if not content:
            return prompt
        # Strip metadata header if present
        if content.startswith("<!--"):
            try:
                end = content.index("-->")
                content = content[end + 3:].strip()
            except ValueError:
                pass
        if len(content) > 4000:
            content = content[:4000] + "\n\n[...truncated...]"
        prompt = (
            f"{prompt}\n\n"
            f"## Recent Project Digest\n\n"
            f"The following is a synthesis of recent exploration work across this project. "
            f"Use it to avoid duplicating known findings and to build on accumulated understanding:\n\n"
            f"{content}"
        )
    except Exception:
        pass  # Best-effort — never block exploration for digest injection
    return prompt


def _inject_siblings(
    prompt: str,
    elmer_dir: Path,
    current_slug: str,
) -> str:
    """Append a brief summary of in-flight sibling explorations (G2).

    Prevents parallel explorations from duplicating analysis or proposing
    conflicting changes by making each worker aware of what others are doing.
    """
    try:
        conn = state.get_db(elmer_dir)
        explorations = state.list_explorations(conn)
        conn.close()

        siblings = []
        for exp in explorations:
            if exp["id"] == current_slug:
                continue
            if exp["status"] in ("running", "pending", "amending"):
                topic = exp["topic"]
                if len(topic) > 120:
                    topic = topic[:117] + "..."
                siblings.append(
                    f"- [{exp['status']}] {topic} (archetype: {exp['archetype']})"
                )

        if not siblings:
            return prompt

        sibling_text = "\n".join(siblings[:15])  # Cap at 15 siblings
        prompt = (
            f"{prompt}\n\n"
            f"## Other In-Flight Explorations\n\n"
            f"These explorations are currently running in parallel. "
            f"Avoid duplicating their analysis or proposing conflicting changes:\n\n"
            f"{sibling_text}"
        )
    except Exception:
        pass  # Best-effort
    return prompt


def _inject_decline_reasons(
    prompt: str,
    topic: str,
    elmer_dir: Path,
) -> str:
    """Inject decline reasons from similar past topics (G3).

    When an exploration's topic keywords match previously declined topics,
    their decline reasons are injected so the worker can avoid repeating
    approaches that were already rejected.
    """
    try:
        # Tokenize the current topic into keywords
        keywords = set(
            w.lower() for w in re.split(r"[^a-zA-Z0-9]+", topic)
            if len(w) >= 4
        )
        if not keywords:
            return prompt

        conn = state.get_db(elmer_dir)
        explorations = state.list_explorations(conn)
        conn.close()

        # Also check archive for cleaned records
        archived = digest_mod._load_archived_proposals(elmer_dir)

        matches: list[tuple[str, str]] = []  # (topic, reason)

        # Check DB records
        for exp in explorations:
            if exp["status"] != "declined":
                continue
            reason = ""
            try:
                reason = exp["decline_reason"] or ""
            except (KeyError, IndexError):
                pass
            if not reason:
                continue
            exp_keywords = set(
                w.lower() for w in re.split(r"[^a-zA-Z0-9]+", exp["topic"])
                if len(w) >= 4
            )
            if keywords & exp_keywords:
                matches.append((exp["topic"], reason))

        # Check archive
        for meta in archived:
            if meta.get("status") != "declined":
                continue
            reason = meta.get("decline_reason", "")
            if not reason:
                continue
            atopic = meta.get("topic", "")
            exp_keywords = set(
                w.lower() for w in re.split(r"[^a-zA-Z0-9]+", atopic)
                if len(w) >= 4
            )
            if keywords & exp_keywords:
                # Deduplicate with DB matches
                if not any(m[0] == atopic for m in matches):
                    matches.append((atopic, reason))

        if not matches:
            return prompt

        # Cap at 3 entries, 500 chars total
        entries = []
        total_chars = 0
        for mtopic, mreason in matches[:3]:
            entry = f"- **{mtopic}**: {mreason}"
            if total_chars + len(entry) > 500:
                break
            entries.append(entry)
            total_chars += len(entry)

        if entries:
            prompt = (
                f"{prompt}\n\n"
                f"## Prior Declined Approaches\n\n"
                f"These related explorations were previously declined. "
                f"Avoid repeating the same approaches:\n\n"
                + "\n".join(entries)
            )
    except Exception:
        pass  # Best-effort
    return prompt


def _resolve_agent_and_prompt(
    archetype: str,
    topic: str,
    elmer_dir: Path,
    project_dir: Path,
    worktree_path: Optional[Path] = None,
    slug: Optional[str] = None,
) -> tuple[dict, str]:
    """Resolve agent config and build the prompt for an exploration.

    Returns (agent_config, topic_prompt) — the topic is the prompt,
    the agent's system prompt provides the methodology.

    Raises RuntimeError if no agent definition exists for the archetype.

    If worktree_path is provided, appends an explicit PROPOSAL.md path
    directive to prevent Claude from writing to the wrong directory.
    """
    agent_config = config.resolve_agent(project_dir, archetype)

    if agent_config is None:
        raise RuntimeError(
            f"No agent definition found for archetype '{archetype}'. "
            f"Ensure elmer-{archetype}.md exists in .claude/agents/ or "
            f"src/elmer/agents/."
        )

    # Agent provides the methodology via system prompt.
    # The -p prompt is just the topic, with optional enrichments.
    prompt = topic
    prompt = _inject_insights(prompt, topic, elmer_dir, project_dir)
    prompt = _inject_digest(prompt, elmer_dir)                         # G1
    prompt = _inject_siblings(prompt, elmer_dir, slug or "")           # G2
    prompt = _inject_decline_reasons(prompt, topic, elmer_dir)         # G3
    if worktree_path is not None:
        prompt = _append_proposal_path(prompt, worktree_path)
    return agent_config, prompt


def _append_proposal_path(prompt: str, worktree_path: Path) -> str:
    """Append an explicit absolute PROPOSAL.md path directive to the prompt."""
    abs_path = worktree_path.resolve()
    return (
        f"{prompt}\n\n"
        f"IMPORTANT: Write your proposal to the absolute path: "
        f"{abs_path}/PROPOSAL.md — do not use a relative path."
    )


def _run_setup_cmd(setup_cmd: str, worktree_path: Path) -> None:
    """Run a setup command in a worktree before the claude session starts.

    Used for dependency installation (e.g., pnpm install) so the worktree
    has all dependencies available when the implementation agent begins.
    Runs synchronously with a 5-minute timeout. Failures are non-fatal
    (the agent can still run install itself), but logged as warnings.
    """
    import subprocess
    try:
        result = subprocess.run(
            setup_cmd,
            shell=True,
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            import logging
            logging.getLogger("elmer").warning(
                "setup_cmd failed (exit %d) in %s: %s",
                result.returncode, worktree_path,
                (result.stderr or result.stdout)[:300],
            )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        import logging
        logging.getLogger("elmer").warning(
            "setup_cmd error in %s: %s", worktree_path, e,
        )


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
    on_approve: Optional[str] = None,
    on_decline: Optional[str] = None,
    slug_override: Optional[str] = None,
    verify_cmd: Optional[str] = None,
    plan_id: Optional[str] = None,
    plan_step: Optional[int] = None,
    setup_cmd: Optional[str] = None,
    blocked_by: Optional[str] = None,
) -> tuple[str, str]:
    """Start a new exploration. Returns (slug, archetype_used).

    If auto_archetype is True, AI selects the best archetype for the topic
    before the exploration starts. The selection cost is tracked.

    If depends_on contains IDs of explorations that aren't yet approved,
    the exploration is created in 'pending' status and launched later
    by schedule_ready().

    If generate_prompt is True, uses two-stage prompt generation: AI generates
    the exploration prompt (Stage 1) before spawning the worker (Stage 2).

    on_approve/on_decline are shell commands executed after approval/declining.
    $ID and $TOPIC are substituted with the exploration ID and topic.

    verify_cmd: shell command run after session completes. Exit 0 = pass.
    On failure, auto-amends up to [verification] max_retries times (ADR-038).

    plan_id/plan_step: link this exploration to an implementation plan.

    setup_cmd: shell command run in the worktree after creation, before
    spawning the claude session. Used for dependency installation (ADR-044).

    blocked_by: comma-separated external blocker IDs. Exploration stays
    pending until all referenced blockers are resolved (ADR-065).
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

    # Validate agent definition exists (fail early, before creating worktree)
    if not generate_prompt and config.resolve_agent(project_dir, archetype) is None:
        conn.close()
        raise RuntimeError(
            f"No agent definition for archetype '{archetype}'. "
            f"Ensure elmer-{archetype}.md exists in .claude/agents/ or src/elmer/agents/."
        )

    # Generate unique slug (or use explicit override for ensemble replicas)
    if slug_override:
        slug = slug_override
    else:
        base_slug = slugify(topic)
        if not base_slug:
            base_slug = "exploration"
        slug = _make_unique_slug(conn, base_slug, elmer_dir)

    branch = f"elmer/{slug}"
    worktree_path = elmer_dir / "worktrees" / slug
    log_path = elmer_dir / "logs" / f"{slug}.log"

    # Validate dependencies exist
    if depends_on:
        for dep_id in depends_on:
            if state.get_exploration(conn, dep_id) is None:
                conn.close()
                raise RuntimeError(f"Dependency '{dep_id}' not found.")

    # Check for dependency cycles before committing any resources
    if depends_on:
        for dep_id in depends_on:
            if state.would_create_cycle(conn, slug, dep_id):
                conn.close()
                raise RuntimeError(
                    f"Dependency cycle detected: '{slug}' -> '{dep_id}' "
                    f"would create a circular dependency."
                )

    # Check if blocked by unmet dependencies or external blockers
    blocked = False
    if depends_on:
        for dep_id in depends_on:
            dep = state.get_exploration(conn, dep_id)
            if dep["status"] != "approved":
                blocked = True
                break

    # External blockers (ADR-065): check if any referenced blockers are unresolved
    if not blocked and blocked_by:
        for bid in (b.strip() for b in blocked_by.split(",")):
            blocker = state.get_blocker(conn, bid)
            if blocker is None or blocker["status"] == "blocked":
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
            on_approve=on_approve,
            on_decline=on_decline,
            verify_cmd=verify_cmd,
            plan_id=plan_id,
            plan_step=plan_step,
            setup_cmd=setup_cmd,
            blocked_by=blocked_by,
        )
        for dep_id in (depends_on or []):
            state.add_dependency(conn, slug, dep_id)
        conn.close()
        return slug, archetype

    # Not blocked — start immediately
    if worktree.branch_exists(project_dir, branch):
        conn.close()
        raise RuntimeError(
            f"Branch '{branch}' already exists. "
            f"Use 'elmer clean' or 'elmer decline {slug}' first."
        )

    agent_config = None

    if generate_prompt:
        prompt, gen_result = promptgen.generate_prompt(
            topic=topic,
            archetype=archetype,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
        )
        prompt = _append_proposal_path(prompt, worktree_path)
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
        agent_config, prompt = _resolve_agent_and_prompt(
            archetype, topic, elmer_dir, project_dir,
            worktree_path=worktree_path,
            slug=slug,
        )
    worktree.create_worktree(project_dir, branch, worktree_path)

    # Run setup command before spawning worker (ADR-044: dependency installation)
    if setup_cmd:
        _run_setup_cmd(setup_cmd, worktree_path)

    pid = worker.spawn_claude(
        prompt=prompt,
        cwd=worktree_path,
        model=model,
        log_path=log_path,
        max_turns=max_turns,
        agent_config=agent_config,
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
        on_approve=on_approve,
        on_decline=on_decline,
        verify_cmd=verify_cmd,
        plan_id=plan_id,
        plan_step=plan_step,
        setup_cmd=setup_cmd,
    )

    # Record dependencies even if all satisfied (for lineage tracking)
    if depends_on:
        for dep_id in depends_on:
            state.add_dependency(conn, slug, dep_id)

    conn.close()
    return slug, archetype


def start_ensemble(
    *,
    topic: str,
    replicas: int,
    archetype: str,
    model: str,
    max_turns: int,
    elmer_dir: Path,
    project_dir: Path,
    archetypes: Optional[list[str]] = None,
    models: Optional[list[str]] = None,
    auto_approve: bool = False,
    generate_prompt: bool = False,
    auto_archetype: bool = False,
) -> list[tuple[str, str]]:
    """Start an ensemble of N explorations on the same topic.

    Returns list of (slug, archetype_used) for each replica.

    archetypes: rotate through these archetypes for replicas.
        If None, all replicas use the same archetype.
    models: rotate through these models for replicas.
        If None, all replicas use the same model.
    """
    if replicas < 2:
        raise RuntimeError("Ensemble requires at least 2 replicas.")

    # Determine the ensemble_id from the topic slug
    ensemble_id = slugify(topic) or "ensemble"
    conn = state.get_db(elmer_dir)
    ensemble_id = _make_unique_slug(conn, ensemble_id, elmer_dir)
    conn.close()

    results = []
    for i in range(replicas):
        # Explicit numbered slug: ensemble_id-1, ensemble_id-2, etc.
        replica_slug = f"{ensemble_id}-{i + 1}"

        # Rotate archetypes if provided
        use_archetype = archetype
        use_auto_archetype = auto_archetype
        if archetypes:
            use_archetype = archetypes[i % len(archetypes)]
            use_auto_archetype = False  # explicit list overrides auto

        # Rotate models if provided
        use_model = model
        if models:
            use_model = models[i % len(models)]

        slug, archetype_used = start_exploration(
            topic=topic,
            archetype=use_archetype,
            model=use_model,
            max_turns=max_turns,
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            auto_approve=False,  # replicas are never individually approved
            generate_prompt=generate_prompt,
            auto_archetype=use_auto_archetype,
            slug_override=replica_slug,
        )

        # Set ensemble metadata on the created exploration
        conn = state.get_db(elmer_dir)
        state.update_exploration(
            conn, slug,
            ensemble_id=ensemble_id,
            ensemble_role="replica",
        )
        conn.close()

        results.append((slug, archetype_used))

    return results


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

    use_generate = bool(exp["generate_prompt"])
    agent_config = None

    if use_generate:
        try:
            prompt, gen_result = promptgen.generate_prompt(
                topic=topic,
                archetype=archetype,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
            )
            prompt = _append_proposal_path(prompt, worktree_path)
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
            # Fall back to agent resolution if prompt generation fails
            agent_config, prompt = _resolve_agent_and_prompt(
                archetype, topic, elmer_dir, project_dir,
                worktree_path=worktree_path,
                slug=exploration_id,
            )
    else:
        agent_config, prompt = _resolve_agent_and_prompt(
            archetype, topic, elmer_dir, project_dir,
            worktree_path=worktree_path,
            slug=exploration_id,
        )

    if worktree.branch_exists(project_dir, branch):
        state.update_exploration(conn, exploration_id, status="failed",
                                 proposal_summary="(branch conflict on deferred start)")
        conn.close()
        return

    worktree.create_worktree(project_dir, branch, worktree_path)

    # Run setup command before spawning worker (ADR-044: dependency installation)
    setup_cmd = exp["setup_cmd"] if "setup_cmd" in exp.keys() else None
    if setup_cmd:
        _run_setup_cmd(setup_cmd, worktree_path)

    pid = worker.spawn_claude(
        prompt=prompt,
        cwd=worktree_path,
        model=model,
        log_path=log_path,
        max_turns=max_turns,
        agent_config=agent_config,
    )

    state.update_exploration(conn, exploration_id, status="running", pid=pid)
    conn.close()


def _build_amend_prompt(
    feedback: str,
    proposal_text: str,
    agent_config: Optional[dict],
) -> str:
    """Assemble the prompt for an amend session."""
    if agent_config is not None:
        return (
            f"## Current PROPOSAL.md\n\n{proposal_text}\n\n"
            f"## Editorial Direction\n\n{feedback}"
        )
    return (
        f"Revise the PROPOSAL.md in the current directory based on "
        f"this editorial direction:\n\n{feedback}\n\n"
        f"Current content:\n\n{proposal_text}\n\n"
        f"Apply the changes, update cross-references, and ensure coherence."
    )


def preview_amend_prompt(
    *,
    exploration_id: str,
    feedback: str,
    elmer_dir: Path,
    project_dir: Path,
) -> dict:
    """Preview the amend prompt without spawning a session.

    Returns a dict with the assembled prompt, agent config (if any),
    and exploration metadata. Validates the same preconditions as
    amend_exploration() but does not modify state or spawn a process.
    """
    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)

    if exp is None:
        conn.close()
        raise RuntimeError(f"Exploration '{exploration_id}' not found.")

    if exp["status"] not in ("done", "failed"):
        conn.close()
        raise RuntimeError(
            f"Cannot amend exploration in status '{exp['status']}'. "
            f"Must be 'done' or 'failed'."
        )

    worktree_path = Path(exp["worktree_path"])
    if not worktree_path.exists():
        conn.close()
        raise RuntimeError(
            f"Worktree not found at {worktree_path}. "
            f"Cannot amend — the branch may have been cleaned up."
        )

    conn.close()

    proposal_path = worktree_path / "PROPOSAL.md"
    proposal_text = proposal_path.read_text() if proposal_path.exists() else "(no PROPOSAL.md found)"

    agent_config = config.resolve_meta_agent(project_dir, "amend")
    prompt = _build_amend_prompt(feedback, proposal_text, agent_config)

    return {
        "prompt": prompt,
        "agent": agent_config.get("name") if agent_config else None,
        "model": exp["model"],
    }


def amend_exploration(
    *,
    exploration_id: str,
    feedback: str,
    elmer_dir: Path,
    project_dir: Path,
    model: Optional[str] = None,
    max_turns: int = 10,
) -> int:
    """Amend a completed exploration's proposal based on editorial feedback.

    Spawns a Claude session in the existing worktree to revise PROPOSAL.md.
    The exploration must be in 'done' or 'failed' status.
    Returns the PID of the spawned process.
    """
    if not worker.check_claude_available():
        raise RuntimeError(
            "claude CLI not found in PATH. Install Claude Code first."
        )

    conn = state.get_db(elmer_dir)
    exp = state.get_exploration(conn, exploration_id)

    if exp is None:
        conn.close()
        raise RuntimeError(f"Exploration '{exploration_id}' not found.")

    if exp["status"] not in ("done", "failed"):
        conn.close()
        raise RuntimeError(
            f"Cannot amend exploration in status '{exp['status']}'. "
            f"Must be 'done' or 'failed'."
        )

    worktree_path = Path(exp["worktree_path"])
    if not worktree_path.exists():
        conn.close()
        raise RuntimeError(
            f"Worktree not found at {worktree_path}. "
            f"Cannot amend — the branch may have been cleaned up."
        )

    # Read current proposal for context in the prompt
    proposal_path = worktree_path / "PROPOSAL.md"
    proposal_text = proposal_path.read_text() if proposal_path.exists() else "(no PROPOSAL.md found)"

    # Resolve the amend agent
    agent_config = config.resolve_meta_agent(project_dir, "amend")
    prompt = _build_amend_prompt(feedback, proposal_text, agent_config)

    use_model = model or exp["model"]
    log_path = elmer_dir / "logs" / f"{exploration_id}.log"

    pid = worker.spawn_claude(
        prompt=prompt,
        cwd=worktree_path,
        model=use_model,
        log_path=log_path,
        max_turns=max_turns,
        agent_config=agent_config,
    )

    state.update_exploration(conn, exploration_id, status="amending", pid=pid)
    conn.close()

    return pid


def schedule_ready(elmer_dir: Path, project_dir: Path) -> list[str]:
    """Find pending explorations with all dependencies met and launch them.

    Also detects and cascades failures: pending explorations whose dependencies
    have failed or been declined are marked as failed themselves (ADR-041).
    Stale pending explorations past their TTL are auto-cancelled (ADR-058).
    """
    conn = state.get_db(elmer_dir)

    # Auto-cancel stale pending explorations (ADR-058)
    cfg = config.load_config(elmer_dir)
    pending_ttl_days = cfg.get("session", {}).get("pending_ttl_days", 7)
    if pending_ttl_days > 0:
        stale = state.get_stale_pending(conn, max_age_hours=pending_ttl_days * 24)
        for exp in stale:
            state.update_exploration(
                conn, exp["id"],
                status="failed",
                completed_at=datetime.now(timezone.utc).isoformat(),
                proposal_summary=f"(auto-cancelled: pending > {pending_ttl_days}d)",
            )
            plan_id = exp["plan_id"] if "plan_id" in exp.keys() else None
            if plan_id:
                state.update_plan(conn, plan_id, status="paused")

    # Cascade failures — mark blocked explorations before scheduling.
    # Log each cascade so operators can see the failure propagation (ADR-066).
    import logging as _logging
    _cascade_logger = _logging.getLogger("elmer.cascade")

    blocked = state.get_pending_blocked(conn)
    if blocked:
        _cascade_logger.warning(
            "CASCADE: %d exploration(s) have failed/declined dependencies", len(blocked),
        )
    for exp in blocked:
        dep_ids = state.get_dependencies(conn, exp["id"])
        failed_deps = []
        for dep_id in dep_ids:
            dep = state.get_exploration(conn, dep_id)
            if dep and dep["status"] in ("failed", "declined"):
                failed_deps.append(dep_id)
        dep_str = ", ".join(failed_deps)
        _cascade_logger.warning(
            "  CASCADE FAIL: %s — blocked by: %s", exp["id"], dep_str,
        )
        state.update_exploration(
            conn, exp["id"],
            status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            proposal_summary=f"(dependency failed: {dep_str})",
        )
        # Pause the plan if this belongs to one
        plan_id = exp["plan_id"] if "plan_id" in exp.keys() else None
        if plan_id:
            state.update_plan(conn, plan_id, status="paused")
            _cascade_logger.warning("  CASCADE PAUSE: plan %s paused", plan_id)

    # External dependency check (ADR-065): skip explorations whose
    # blocked_by references unresolved external blockers.
    externally_blocked_ids: set[str] = set()
    try:
        ext_blocked = state.get_externally_blocked(conn)
        externally_blocked_ids = {e["id"] for e in ext_blocked}
    except Exception:
        pass  # Table may not exist in older DBs

    ready = state.get_pending_ready(conn)
    conn.close()

    launched = []
    for exp in ready:
        if exp["id"] in externally_blocked_ids:
            continue  # Skip — waiting on external decision
        launch_pending(
            exploration_id=exp["id"],
            elmer_dir=elmer_dir,
            project_dir=project_dir,
        )
        launched.append(exp["id"])

    return launched
