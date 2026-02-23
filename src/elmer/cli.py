"""Elmer CLI — Autonomous research with branching."""

import os
import sys
from pathlib import Path

import click

from . import archstats, batch as batch_mod, config, costs as costs_mod, daemon as daemon_mod, dashboard, explore as explore_mod, gate, generate as gen_mod, insights as insights_mod, invariants as inv_mod, pr as pr_mod, questions as questions_mod, review as review_mod, scaffold, skill_scaffold, state, worktree as wt


@click.group()
@click.version_option()
def cli():
    """Elmer — Autonomous research with branching.

    "Be vewy vewy quiet, I'm hunting insights."

    Create git branches, spawn Claude Code sessions to explore topics
    autonomously, and queue proposals for review. Approve to merge.
    Reject to discard.
    """


def _require_project() -> Path:
    """Find project root or exit."""
    try:
        return wt.get_project_root()
    except RuntimeError:
        click.echo("Error: not in a git repository.", err=True)
        sys.exit(1)


def _require_elmer(project_dir: Path) -> Path:
    """Find .elmer/ or exit."""
    elmer_dir = project_dir / ".elmer"
    if not elmer_dir.exists():
        click.echo("Error: .elmer/ not found. Run 'elmer init' first.", err=True)
        sys.exit(1)
    # Ensure project is in global registry
    config.register_project(project_dir)
    return elmer_dir


# --- Commands ---


@cli.command()
@click.option("--docs", is_flag=True, help="Scaffold the five-document pattern (CLAUDE.md, DESIGN.md, DECISIONS.md, ROADMAP.md, CONTEXT.md)")
@click.option("--skills", is_flag=True, help="Scaffold project-specific Claude Code skills in .claude/skills/")
def init(docs, skills):
    """Initialize Elmer in the current project.

    With --docs, scaffolds the five-document pattern that makes projects
    effective with Claude Code: CLAUDE.md, DESIGN.md, DECISIONS.md,
    ROADMAP.md, CONTEXT.md. Only creates files that don't already exist.

    With --skills, detects project characteristics from existing docs and
    generates Claude Code skills in .claude/skills/. Skills provide
    interactive analysis lenses (e.g., /mission-align, /cultural-lens)
    that complement Elmer's autonomous exploration archetypes.
    """
    project_dir = _require_project()
    elmer_dir = config.init_project(project_dir)
    click.echo(f"Initialized .elmer/ in {project_dir}")
    click.echo(f"  Config:     {elmer_dir / 'config.toml'}")
    click.echo(f"  Archetypes: {elmer_dir / 'archetypes/'}")

    if docs:
        created = scaffold.scaffold_docs(project_dir)
        if created:
            click.echo()
            click.echo("Scaffolded project documents:")
            for f in created:
                click.echo(f"  {f}")
            click.echo()
            click.echo("Edit these files to describe your project.")
        else:
            click.echo()
            click.echo("All five documents already exist — nothing to scaffold.")

    if skills:
        detected = skill_scaffold.detect_skills(project_dir)
        any_detected = any(detected.values())

        if any_detected:
            click.echo()
            click.echo("Detected project signals:")
            for name, found in sorted(detected.items()):
                icon = "+" if found else " "
                click.echo(f"  {icon} {name}")

        created = skill_scaffold.scaffold_skills(project_dir)
        if created:
            click.echo()
            click.echo("Scaffolded Claude Code skills:")
            for name in created:
                click.echo(f"  .claude/skills/{name}/SKILL.md")
            click.echo()
            click.echo("Use /{name} in Claude Code sessions for interactive analysis.")
        elif any_detected:
            click.echo()
            click.echo("All detected skills already exist — nothing to scaffold.")
        else:
            click.echo()
            click.echo("No project-specific skills detected from project docs.")
            click.echo("Add project documentation first (elmer init --docs), then re-run with --skills.")

    if not docs and not skills:
        click.echo()
        click.echo("Edit .elmer/config.toml to change defaults.")
        click.echo("Add custom archetypes to .elmer/archetypes/.")
        click.echo("Use 'elmer init --docs' to scaffold project documentation.")
        click.echo("Use 'elmer init --skills' to scaffold Claude Code skills.")


@cli.command()
@click.argument("topic", required=False)
@click.option("-a", "--archetype", default=None, help="Archetype template (default: from config). Overrides --auto-archetype.")
@click.option("-m", "--model", default=None, help="Model: sonnet, opus, haiku (default: from config)")
@click.option("-f", "--file", "topics_file", type=click.Path(exists=True), help="File with one topic per line")
@click.option("--max-turns", default=None, type=int, help="Max turns for claude session")
@click.option("--depends-on", "depends_on", multiple=True, help="Wait for this exploration to be approved first (repeatable)")
@click.option("--auto-approve", is_flag=True, help="Auto-approve via AI review when done")
@click.option("--auto-archetype", is_flag=True, default=False, help="AI selects the best archetype for each topic")
@click.option("--generate-prompt", is_flag=True, default=False, help="Use AI to generate the exploration prompt (two-stage)")
@click.option("--no-generate", is_flag=True, default=False, help="Use static template (skip two-stage prompt generation)")
@click.option("--budget", "budget_usd", default=None, type=float, help="Max cost in USD for this exploration")
@click.option("--on-approve", default=None, help="Shell command to run on approval ($ID, $TOPIC substituted)")
@click.option("--on-reject", default=None, help="Shell command to run on rejection ($ID, $TOPIC substituted)")
def explore(topic, archetype, model, topics_file, max_turns, depends_on, auto_approve, auto_archetype, generate_prompt, no_generate, budget_usd, on_approve, on_reject):
    """Start an exploration on a new branch.

    Each exploration gets its own git worktree and a background Claude
    session that writes a PROPOSAL.md when done.

    Use --auto-archetype to let AI pick the best archetype for the topic.
    Use -a to force a specific archetype (overrides --auto-archetype).
    Use --generate-prompt for AI-generated exploration prompts (two-stage).

    \b
    Examples:
        elmer explore "evaluate COT positioning data"
        elmer explore "prototype search API" -a prototype -m opus
        elmer explore -f topics.txt
        elmer explore "follow-up analysis" --depends-on my-first-topic
        elmer explore "deep analysis" --auto-archetype --generate-prompt
        elmer explore "topic" --budget 2.00
        elmer explore "topic" --on-approve "elmer generate --follow-up \\$ID"
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    if not topic and not topics_file:
        click.echo("Error: provide a topic or --file.", err=True)
        sys.exit(1)

    cfg = config.load_config(elmer_dir)
    defaults = cfg.get("defaults", {})

    # -a forces a specific archetype and disables auto-selection
    use_auto_archetype = auto_archetype and archetype is None
    archetype = archetype or defaults.get("archetype", "explore-act")
    model = model or defaults.get("model", "sonnet")
    max_turns = max_turns or defaults.get("max_turns", 50)

    # Resolve two-stage prompt generation: CLI flags override config default
    if no_generate:
        use_generate = False
    elif generate_prompt:
        use_generate = True
    else:
        use_generate = defaults.get("generate_prompt", False)

    # Budget: CLI flag overrides config default
    if budget_usd is None:
        budget_usd = defaults.get("budget_usd")

    dep_list = list(depends_on) if depends_on else None

    # Collect topics
    topics: list[str] = []
    if topics_file:
        with open(topics_file) as f:
            topics = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    if topic:
        topics.append(topic)

    for t in topics:
        try:
            slug, archetype_used = explore_mod.start_exploration(
                topic=t,
                archetype=archetype,
                model=model,
                max_turns=max_turns,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                depends_on=dep_list,
                auto_approve=auto_approve,
                auto_archetype=use_auto_archetype,
                generate_prompt=use_generate,
                budget_usd=budget_usd,
                on_approve=on_approve,
                on_reject=on_reject,
            )
            click.echo(f"Started: {slug}")
            click.echo(f"  Branch:    elmer/{slug}")
            click.echo(f"  Archetype: {archetype_used}" + (" (AI-selected)" if use_auto_archetype else ""))
            click.echo(f"  Model:     {model}")
            if dep_list:
                click.echo(f"  Depends on: {', '.join(dep_list)}")
            if auto_approve:
                click.echo(f"  Auto-approve: enabled")
            if use_generate:
                click.echo(f"  Prompt:    AI-generated (two-stage)")
            if budget_usd is not None:
                click.echo(f"  Budget:    ${budget_usd:.2f}")
            if on_approve:
                click.echo(f"  On approve: {on_approve}")
            if on_reject:
                click.echo(f"  On reject:  {on_reject}")
            click.echo(f"  Log:       .elmer/logs/{slug}.log")
            click.echo()
        except (RuntimeError, FileNotFoundError) as e:
            click.echo(f"Error: {e}", err=True)


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("-a", "--archetype", default=None, help="Override archetype (default: inferred from filename)")
@click.option("-m", "--model", default=None, help="Model: sonnet, opus, haiku (default: from config)")
@click.option("--max-turns", default=None, type=int, help="Max turns for claude sessions")
@click.option("--chain", is_flag=True, help="Run topics sequentially — each depends on the previous")
@click.option("--dry-run", is_flag=True, help="Parse and display topics without spawning explorations")
@click.option("--item", default=None, type=int, help="Run only item N (1-indexed)")
@click.option("--auto-approve", is_flag=True, help="Auto-approve via AI review when done")
@click.option("--auto-archetype", is_flag=True, default=False, help="AI selects the best archetype per topic (overrides filename inference)")
@click.option("--generate-prompt", is_flag=True, default=False, help="Use AI to generate exploration prompts (two-stage)")
@click.option("--budget", "budget_usd", default=None, type=float, help="Total budget in USD (divided across topics)")
def batch(file, archetype, model, max_turns, chain, dry_run, item, auto_approve, auto_archetype, generate_prompt, budget_usd):
    """Run explorations from a topic list file.

    Topic list files are markdown documents with --- separators.
    The archetype is inferred from the filename: .elmer/explore-act.md
    uses the explore-act archetype.

    With --chain, topics run sequentially — each exploration depends on
    the previous one, so merges never conflict. Without --chain, all
    topics launch in parallel.

    \b
    File format:
        # Optional header (ignored)
        ---
        First topic
        ---
        Second topic (can be multi-line)
        ---

    \b
    Examples:
        elmer batch .elmer/explore-act.md              # spawn all topics
        elmer batch .elmer/explore-act.md --dry-run    # preview parsed topics
        elmer batch .elmer/explore-act.md --chain      # sequential execution
        elmer batch .elmer/explore-act.md --item 2     # run only item 2
        elmer batch .elmer/prototype.md -m opus        # override model
        elmer batch .elmer/explore-act.md --budget 10  # $10 divided across topics
    """
    from pathlib import Path as P

    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    file_path = P(file)
    topics = batch_mod.parse_topic_file(file_path)

    if not topics:
        click.echo("No topics found in file.", err=True)
        sys.exit(1)

    # Resolve archetype: CLI flag > --auto-archetype > filename inference
    use_auto_archetype = auto_archetype and archetype is None
    if archetype is None and not auto_archetype:
        archetype = batch_mod.archetype_from_filename(file_path)
    elif archetype is None:
        # auto-archetype mode — need a fallback for start_exploration
        cfg = config.load_config(elmer_dir)
        archetype = cfg.get("defaults", {}).get("archetype", "explore-act")

    # Validate archetype exists (unless auto-archetype will override it)
    if not use_auto_archetype:
        try:
            config.resolve_archetype(elmer_dir, archetype)
        except FileNotFoundError as e:
            click.echo(f"Error: {e}", err=True)
            click.echo(f"Filename '{file_path.stem}' doesn't match a known archetype. Use -a to specify one.", err=True)
            sys.exit(1)

    cfg = config.load_config(elmer_dir)
    defaults = cfg.get("defaults", {})
    model = model or defaults.get("model", "sonnet")
    max_turns = max_turns or defaults.get("max_turns", 50)

    # Handle --item filter
    if item is not None:
        if item < 1 or item > len(topics):
            click.echo(f"Error: --item {item} out of range (1-{len(topics)}).", err=True)
            sys.exit(1)
        topics = [topics[item - 1]]
        click.echo(f"Selected item {item}.")
        click.echo()

    # Display parsed topics
    click.echo(f"Topic list: {file_path}")
    click.echo(f"Archetype:  {archetype}" + (" (AI-selected per topic)" if use_auto_archetype else ""))
    click.echo(f"Topics:     {len(topics)}")
    if chain:
        click.echo(f"Mode:       sequential (chained)")
    click.echo()

    for i, topic in enumerate(topics, 1):
        # Truncate display for long multi-line topics
        display = topic.replace("\n", " ")
        if len(display) > 100:
            display = display[:97] + "..."
        click.echo(f"  {i}. {display}")
    click.echo()

    if dry_run:
        click.echo("Dry run — no explorations spawned.")
        return

    # Resolve two-stage prompt generation
    use_generate = generate_prompt or defaults.get("generate_prompt", False)

    # Divide budget across topics
    per_topic_budget = None
    if budget_usd is not None:
        per_topic_budget = budget_usd / len(topics)
        click.echo(f"Budget per topic: ${per_topic_budget:.2f}")
        click.echo()

    # Spawn explorations
    previous_slug = None
    for i, topic in enumerate(topics):
        dep_list = None
        if chain and previous_slug is not None:
            dep_list = [previous_slug]

        try:
            slug, archetype_used = explore_mod.start_exploration(
                topic=topic,
                archetype=archetype,
                model=model,
                max_turns=max_turns,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                depends_on=dep_list,
                auto_approve=auto_approve,
                auto_archetype=use_auto_archetype,
                generate_prompt=use_generate,
                budget_usd=per_topic_budget,
            )
            click.echo(f"Started: {slug}")
            click.echo(f"  Branch:    elmer/{slug}")
            click.echo(f"  Archetype: {archetype_used}" + (" (AI-selected)" if use_auto_archetype else ""))
            if chain and previous_slug:
                click.echo(f"  Depends on: {previous_slug}")
            if auto_approve:
                click.echo(f"  Auto-approve: enabled")
            if per_topic_budget is not None:
                click.echo(f"  Budget:    ${per_topic_budget:.2f}")
            click.echo()

            previous_slug = slug
        except (RuntimeError, FileNotFoundError) as e:
            click.echo(f"Error spawning topic {i + 1}: {e}", err=True)
            if chain:
                click.echo("Chain broken — stopping.", err=True)
                break

    click.echo(f"Batch complete.")
    if chain:
        click.echo("Topics are chained — each starts after the previous is approved.")
        click.echo("Use 'elmer approve ID' to advance the chain, or 'elmer approve --all' for each step.")


@cli.command()
@click.option("--count", default=None, type=int, help="Number of topics to generate (default: 5)")
@click.option("--follow-up", "follow_up_id", default=None, help="Generate follow-ups to a completed exploration")
@click.option("-m", "--model", default=None, help="Model for topic generation (default: from config)")
@click.option("-a", "--archetype", default=None, help="Archetype for spawned explorations (default: from config). Overrides --auto-archetype.")
@click.option("--max-turns", default=None, type=int, help="Max turns for spawned explorations")
@click.option("--dry-run", is_flag=True, help="Print topics without spawning explorations")
@click.option("--auto-approve", is_flag=True, help="Auto-approve spawned explorations via AI review")
@click.option("--auto-archetype", is_flag=True, default=False, help="AI selects the best archetype per topic")
@click.option("--generate-prompt", is_flag=True, default=False, help="Use AI to generate exploration prompts (two-stage)")
@click.option("--no-generate", is_flag=True, default=False, help="Use static templates (skip two-stage prompt generation)")
@click.option("--budget", "budget_usd", default=None, type=float, help="Total budget in USD (divided across spawned explorations)")
def generate(count, follow_up_id, model, archetype, max_turns, dry_run, auto_approve, auto_archetype, generate_prompt, no_generate, budget_usd):
    """Generate research topics using AI.

    Reads project documentation and exploration history to propose
    topics worth exploring. Each topic is spawned as a separate
    exploration unless --dry-run is used.

    With --auto-archetype, AI picks the best archetype for each topic.
    With --budget, the total is divided evenly across spawned explorations.

    \b
    Examples:
        elmer generate                          # 5 topics, auto-spawn
        elmer generate --count 3 --dry-run      # Preview 3 topics
        elmer generate --follow-up my-topic     # Follow-ups to a done exploration
        elmer generate -m haiku --count 10      # Cheap broad generation
        elmer generate --budget 5.00            # $1 per exploration (5 topics)
        elmer generate --auto-archetype         # AI picks archetype per topic
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    cfg = config.load_config(elmer_dir)
    gen_cfg = cfg.get("generate", {})
    defaults = cfg.get("defaults", {})

    gen_model = model or gen_cfg.get("model", defaults.get("model", "sonnet"))
    gen_count = count or gen_cfg.get("count", 5)
    gen_max_turns = gen_cfg.get("max_turns", 5)

    # Defaults for spawned explorations
    use_auto_archetype = auto_archetype and archetype is None
    explore_archetype = archetype or defaults.get("archetype", "explore-act")
    explore_model = defaults.get("model", "sonnet")
    explore_max_turns = max_turns or defaults.get("max_turns", 50)

    # Resolve two-stage prompt generation
    if no_generate:
        use_generate = False
    elif generate_prompt:
        use_generate = True
    else:
        use_generate = defaults.get("generate_prompt", False)

    # Budget: CLI flag overrides config default, divide across explorations
    if budget_usd is None:
        budget_usd = gen_cfg.get("budget_usd")

    click.echo(f"Generating {gen_count} topics (model: {gen_model})...")
    if follow_up_id:
        click.echo(f"  Follow-up to: {follow_up_id}")
    if budget_usd is not None:
        click.echo(f"  Total budget: ${budget_usd:.2f}")
    click.echo()

    try:
        topics = gen_mod.generate_topics(
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            count=gen_count,
            follow_up_id=follow_up_id,
            model=gen_model,
            max_turns=gen_max_turns,
        )
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo("Generated topics:")
    for i, topic in enumerate(topics, 1):
        click.echo(f"  {i}. {topic}")
    click.echo()

    if dry_run:
        click.echo("Dry run — no explorations spawned.")
        return

    # Divide budget evenly across explorations
    per_exploration_budget = None
    if budget_usd is not None:
        per_exploration_budget = budget_usd / len(topics)
        click.echo(f"Budget per exploration: ${per_exploration_budget:.2f}")

    click.echo(f"Spawning {len(topics)} exploration(s)...")
    click.echo()

    for topic in topics:
        try:
            slug, archetype_used = explore_mod.start_exploration(
                topic=topic,
                archetype=explore_archetype,
                model=explore_model,
                max_turns=explore_max_turns,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                parent_id=follow_up_id,
                auto_approve=auto_approve,
                auto_archetype=use_auto_archetype,
                generate_prompt=use_generate,
                budget_usd=per_exploration_budget,
            )
            click.echo(f"Started: {slug}")
            click.echo(f"  Branch:    elmer/{slug}")
            click.echo(f"  Archetype: {archetype_used}" + (" (AI-selected)" if use_auto_archetype else ""))
            click.echo(f"  Model:     {explore_model}")
            if follow_up_id:
                click.echo(f"  Parent:    {follow_up_id}")
            if auto_approve:
                click.echo(f"  Auto-approve: enabled")
            if use_generate:
                click.echo(f"  Prompt:    AI-generated (two-stage)")
            if per_exploration_budget is not None:
                click.echo(f"  Budget:    ${per_exploration_budget:.2f}")
            click.echo()
        except (RuntimeError, FileNotFoundError) as e:
            click.echo(f"Error spawning '{topic}': {e}", err=True)


@cli.command()
@click.option("--all-projects", is_flag=True, help="Show status across all registered projects")
def status(all_projects):
    """Show exploration status.

    With --all-projects, shows a summary across all registered Elmer projects
    (projects where 'elmer init' has been run).

    \b
    Examples:
        elmer status                    # Current project status
        elmer status --all-projects     # All projects summary
    """
    if all_projects:
        dashboard.show_all_projects()
        return
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)
    review_mod.show_status(elmer_dir, project_dir)


@cli.command()
@click.argument("exploration_id", required=False)
@click.option("--prioritize", is_flag=True, help="Rank proposals by review priority")
def review(exploration_id, prioritize):
    """Review exploration proposals.

    Without an ID, lists all proposals pending review.
    With an ID, shows the full proposal content.
    With --prioritize, ranks proposals by expected value (blockers,
    staleness, diff size).

    \b
    Examples:
        elmer review                     # List pending proposals
        elmer review --prioritize        # Rank by review priority
        elmer review my-exploration      # Show full proposal
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    if exploration_id:
        review_mod.show_proposal(elmer_dir, exploration_id)
    elif prioritize:
        review_mod.list_proposals_prioritized(elmer_dir, project_dir)
    else:
        review_mod.list_proposals(elmer_dir)


@cli.command()
@click.argument("exploration_id", required=False)
@click.option("--all", "approve_all_flag", is_flag=True, help="Approve all pending proposals")
@click.option("--auto-followup", is_flag=True, help="Generate follow-up topics after approval")
@click.option("--followup-count", default=None, type=int, help="Number of follow-up topics (default: 3)")
@click.option("--validate-invariants", is_flag=True, help="Run document invariant checks after merge")
def approve(exploration_id, approve_all_flag, auto_followup, followup_count, validate_invariants):
    """Approve and merge an exploration.

    Merges the exploration branch into the current branch and cleans up
    the worktree. With --auto-followup, generates follow-up topics and
    spawns them as new explorations.

    With --validate-invariants, runs a document consistency check after
    merge and auto-fixes any violations.

    \b
    Examples:
        elmer approve my-exploration
        elmer approve --all
        elmer approve my-exploration --auto-followup
        elmer approve my-exploration --validate-invariants
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    cfg = config.load_config(elmer_dir)
    fu_cfg = cfg.get("followup", {})

    # Resolve follow-up settings from CLI flags + config
    use_followup = auto_followup or fu_cfg.get("enabled", False)
    fu_count = followup_count or fu_cfg.get("count", 3)
    fu_auto_approve = fu_cfg.get("auto_approve", False)

    if approve_all_flag:
        approved = gate.approve_all(
            elmer_dir, project_dir,
            auto_followup=use_followup,
            followup_count=fu_count,
            followup_auto_approve=fu_auto_approve,
        )
        if approved:
            click.echo(f"Approved {len(approved)} exploration(s): {', '.join(approved)}")
            if validate_invariants:
                _run_invariants(elmer_dir, project_dir, cfg)
        else:
            click.echo("No proposals pending approval.")
        return

    if not exploration_id:
        click.echo("Error: provide an exploration ID or --all.", err=True)
        sys.exit(1)

    gate.approve_exploration(
        elmer_dir, project_dir, exploration_id,
        auto_followup=use_followup,
        followup_count=fu_count,
        followup_auto_approve=fu_auto_approve,
    )
    click.echo(f"Approved and merged: {exploration_id}")

    if validate_invariants:
        _run_invariants(elmer_dir, project_dir, cfg)


def _run_invariants(elmer_dir: Path, project_dir: Path, cfg: dict) -> None:
    """Run document invariant validation and display results."""
    inv_cfg = cfg.get("invariants", {})
    inv_model = inv_cfg.get("model", "sonnet")
    inv_max_turns = inv_cfg.get("max_turns", 5)

    click.echo()
    click.echo("Validating document invariants...")

    try:
        result = inv_mod.validate_invariants(
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=inv_model,
            max_turns=inv_max_turns,
        )

        for check in result.checks:
            icon = "+" if check.passed else "!"
            click.echo(f"  {icon} {check.invariant}")
            if not check.passed:
                click.echo(f"    {check.detail}")

        if result.fixes:
            click.echo()
            for fix in result.fixes:
                click.echo(f"  Fixed: {fix}")

        if result.all_passed:
            click.echo("  All invariants passed.")
    except (RuntimeError, FileNotFoundError) as e:
        click.echo(f"  Invariant validation failed: {e}")


@cli.command()
@click.argument("exploration_id")
def reject(exploration_id):
    """Reject and discard an exploration.

    Deletes the branch and worktree. The exploration is marked as rejected
    in state but the log file is preserved.
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    gate.reject_exploration(elmer_dir, project_dir, exploration_id)
    click.echo(f"Rejected: {exploration_id}")


@cli.command()
@click.argument("exploration_id")
def cancel(exploration_id):
    """Cancel a running or pending exploration.

    Stops the Claude session (if running), removes the worktree and branch,
    and marks the exploration as rejected. The log file is preserved.

    Use this to stop explorations that are burning money on the wrong topic
    or archetype. For completed explorations, use 'elmer reject' instead.
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    gate.cancel_exploration(elmer_dir, project_dir, exploration_id)
    click.echo(f"Cancelled: {exploration_id}")


@cli.command()
def clean():
    """Clean up finished explorations.

    Removes worktrees and state entries for approved and rejected
    explorations. Running and pending explorations are not affected.
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    count = gate.clean_all(elmer_dir, project_dir)
    click.echo(f"Cleaned {count} exploration(s).")


@cli.command()
@click.argument("exploration_id")
def pr(exploration_id):
    """Create a GitHub PR from an exploration.

    Pushes the exploration branch to the remote and creates a PR using
    the gh CLI. The PROPOSAL.md content becomes the PR body.

    Requires the gh CLI: https://cli.github.com/

    \b
    Examples:
        elmer pr my-exploration         # Push branch and create PR
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    try:
        pr_url = pr_mod.create_pr_for_exploration(
            elmer_dir, project_dir, exploration_id,
        )
        click.echo(f"PR created: {pr_url}")
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def tree():
    """Show exploration dependency tree.

    Displays explorations as a tree based on parent-child relationships.
    Root explorations (no parent) appear at the top level, with their
    follow-ups nested below.
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn)
    conn.close()

    if not explorations:
        click.echo("No explorations found.")
        return

    status_icons = {
        "pending": ".",
        "running": "~",
        "done": "*",
        "approved": "+",
        "rejected": "-",
        "failed": "!",
    }

    # Build parent→children map
    by_id = {exp["id"]: exp for exp in explorations}
    children: dict[str, list] = {}
    roots = []

    for exp in explorations:
        pid = exp["parent_id"]
        if pid and pid in by_id:
            children.setdefault(pid, []).append(exp)
        else:
            roots.append(exp)

    def _print_tree(exp, prefix="", is_last=True):
        icon = status_icons.get(exp["status"], " ")
        connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
        if prefix == "":
            click.echo(f"{icon} {exp['id']} [{exp['status']}]")
        else:
            click.echo(f"{prefix}{connector}{icon} {exp['id']} [{exp['status']}]")

        child_list = children.get(exp["id"], [])
        for i, child in enumerate(child_list):
            child_prefix = prefix + ("    " if is_last else "\u2502   ")
            if prefix == "":
                child_prefix = "    "
            _print_tree(child, child_prefix, i == len(child_list) - 1)

    for root in roots:
        _print_tree(root)

    click.echo()
    click.echo(". pending  ~ running  * review ready  + approved  - rejected  ! failed")


@cli.command()
@click.option("--exploration", "exploration_id", default=None, help="Show costs for a single exploration")
def costs(exploration_id):
    """Show cost summary for explorations and meta-operations.

    Displays token usage and cost data extracted from claude session output.
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)
    costs_mod.show_costs(elmer_dir, exploration_id=exploration_id)


@cli.command()
@click.option("-m", "--model", default=None, help="Model for invariant validation (default: sonnet)")
def validate(model):
    """Validate document invariants.

    Checks that project documentation is internally consistent.
    Default rules check ADR counts, phase status, and feature claims.
    Custom rules can be configured in .elmer/config.toml.

    \b
    Examples:
        elmer validate                  # Check with default rules
        elmer validate -m haiku         # Quick check with haiku
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    cfg = config.load_config(elmer_dir)
    inv_cfg = cfg.get("invariants", {})
    inv_model = model or inv_cfg.get("model", "sonnet")
    inv_max_turns = inv_cfg.get("max_turns", 5)

    click.echo(f"Validating document invariants (model: {inv_model})...")
    click.echo()

    try:
        result = inv_mod.validate_invariants(
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=inv_model,
            max_turns=inv_max_turns,
        )

        for check in result.checks:
            icon = "+" if check.passed else "!"
            click.echo(f"  {icon} {check.invariant}")
            if not check.passed:
                click.echo(f"    {check.detail}")

        if result.fixes:
            click.echo()
            for fix in result.fixes:
                click.echo(f"  Fixed: {fix}")

        click.echo()
        passed = sum(1 for c in result.checks if c.passed)
        total = len(result.checks)
        click.echo(f"{passed}/{total} invariants passed.")

        if result.all_passed:
            click.echo("All documents consistent.")
        else:
            click.echo("Some invariants failed — check fixes above.")
    except (RuntimeError, FileNotFoundError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("mine-questions")
@click.option("-m", "--model", default=None, help="Model for question mining (default: from config)")
@click.option("--cluster", default=None, help="Filter to a specific cluster name")
@click.option("--spawn", is_flag=True, help="Spawn explorations from mined questions")
@click.option("--max-per-cluster", default=3, type=int, help="Max questions per cluster to convert to topics (default: 3)")
@click.option("-a", "--archetype", default=None, help="Archetype for spawned explorations (default: from config)")
@click.option("--auto-approve", is_flag=True, help="Auto-approve spawned explorations via AI review")
def mine_questions(model, cluster, spawn, max_per_cluster, archetype, auto_approve):
    """Extract open questions from project documentation.

    Parses CONTEXT.md, DESIGN.md, ROADMAP.md, DECISIONS.md for explicit
    questions and implicit gaps. Groups them by theme.

    With --spawn, converts questions to exploration topics and starts them.

    \b
    Examples:
        elmer mine-questions                           # Show question clusters
        elmer mine-questions --cluster "Architecture"  # Filter by cluster
        elmer mine-questions --spawn                   # Explore all questions
        elmer mine-questions --spawn --cluster "API"   # Explore one cluster
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    cfg = config.load_config(elmer_dir)
    q_cfg = cfg.get("questions", {})
    defaults = cfg.get("defaults", {})
    q_model = model or q_cfg.get("model", defaults.get("model", "opus"))

    click.echo(f"Mining questions (model: {q_model})...")
    click.echo()

    try:
        clusters = questions_mod.mine_questions(
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            model=q_model,
            max_turns=q_cfg.get("max_turns", 5),
        )
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Display clusters
    total = 0
    for name, questions in clusters.items():
        if cluster and cluster.lower() not in name.lower():
            continue
        click.echo(f"CLUSTER: {name}")
        for q in questions:
            click.echo(f"  - {q}")
        click.echo()
        total += len(questions)

    click.echo(f"{total} question(s) in {len(clusters)} cluster(s).")

    if not spawn:
        return

    # Convert to topics and spawn explorations
    topics = questions_mod.clusters_to_topics(
        clusters,
        cluster_filter=cluster,
        max_per_cluster=max_per_cluster,
    )

    if not topics:
        click.echo("No topics to spawn.")
        return

    click.echo()
    click.echo(f"Spawning {len(topics)} exploration(s) from questions...")
    click.echo()

    explore_archetype = archetype or defaults.get("archetype", "explore-act")
    explore_model = defaults.get("model", "opus")
    explore_max_turns = defaults.get("max_turns", 50)

    for topic in topics:
        try:
            slug, archetype_used = explore_mod.start_exploration(
                topic=topic,
                archetype=explore_archetype,
                model=explore_model,
                max_turns=explore_max_turns,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                auto_approve=auto_approve,
            )
            click.echo(f"Started: {slug}")
        except (RuntimeError, FileNotFoundError) as e:
            click.echo(f"Error spawning '{topic}': {e}", err=True)


@cli.command()
def insights():
    """Show cross-project insights.

    Lists all generalizable insights extracted from approved explorations.
    Insights are stored in ~/.elmer/insights.db and shared across projects.
    """
    all_insights = insights_mod.list_all_insights()
    if not all_insights:
        click.echo("No insights recorded yet.")
        click.echo("Enable insights in .elmer/config.toml:")
        click.echo('  [insights]')
        click.echo('  enabled = true')
        return

    click.echo(f"{'#':<4} {'PROJECT':<20} {'INSIGHT':<80}")
    click.echo("-" * 104)

    for i, ins in enumerate(all_insights, 1):
        project = ins["source_project"] or "?"
        text = ins["text"]
        if len(text) > 78:
            text = text[:75] + "..."
        click.echo(f"{i:<4} {project:<20} {text}")

    click.echo(f"\n{len(all_insights)} insight(s) total.")


# --- Archetypes ---


@cli.group()
def archetypes():
    """Manage and analyze archetypes.

    View available archetypes, their effectiveness statistics,
    and recommendations based on historical performance.
    """


@archetypes.command("stats")
def archetypes_stats():
    """Show archetype effectiveness statistics.

    Analyzes historical exploration data to show approval rates,
    average costs, and other metrics per archetype.

    \b
    Examples:
        elmer archetypes stats
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)
    archstats.show_archetype_stats(elmer_dir)


@archetypes.command("list")
def archetypes_list():
    """List available archetypes.

    Shows all archetypes available in the project (local + bundled).
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    local_dir = elmer_dir / "archetypes"
    bundled_dir = config.ARCHETYPES_DIR

    # Collect unique archetype names
    archs: dict[str, str] = {}  # name -> source

    if bundled_dir.exists():
        for f in sorted(bundled_dir.glob("*.md")):
            archs[f.stem] = "bundled"

    if local_dir.exists():
        for f in sorted(local_dir.glob("*.md")):
            if f.stem in archs:
                archs[f.stem] = "local (overrides bundled)"
            else:
                archs[f.stem] = "local"

    if not archs:
        click.echo("No archetypes found.")
        return

    click.echo(f"{'ARCHETYPE':<28} {'SOURCE':<28}")
    click.echo("-" * 56)
    for name, source in sorted(archs.items()):
        click.echo(f"{name:<28} {source:<28}")

    click.echo(f"\n{len(archs)} archetype(s) available.")


# --- Daemon ---


@cli.group(invoke_without_command=True)
@click.option("--interval", default=None, type=int, help="Seconds between cycles (default: 600)")
@click.option("--auto-approve", is_flag=True, help="Auto-approve all explorations via AI review")
@click.option("--generate", "auto_generate", is_flag=True, help="Auto-generate topics when running low")
@click.option("--auto-archetype", is_flag=True, help="AI selects archetype for generated topics")
@click.option("--audit", "audit_enabled", is_flag=True, help="Run scheduled audits (configure in [audit] section)")
@click.option("--budget", "budget_per_cycle", default=None, type=float, help="Max cost per cycle in USD")
@click.option("--max-concurrent", default=None, type=int, help="Max simultaneous explorations (default: 5)")
@click.option("--generate-threshold", default=None, type=int, help="Generate when active < threshold (default: 2)")
@click.option("--generate-count", default=None, type=int, help="Topics to generate per cycle (default: 5)")
@click.option("--auto-followup", is_flag=True, help="Generate follow-up topics after approvals")
@click.option("--followup-count", default=None, type=int, help="Follow-up topics per approval (default: 3)")
@click.pass_context
def daemon(ctx, interval, auto_approve, auto_generate, auto_archetype,
           audit_enabled, budget_per_cycle,
           max_concurrent, generate_threshold, generate_count,
           auto_followup, followup_count):
    """Manage the Elmer daemon for continuous operation.

    Without a subcommand, starts the daemon. Use 'status' or 'stop'
    subcommands to manage a running daemon.

    With --audit, runs scheduled audit archetypes (one per cycle, rotating).
    Configure the schedule in .elmer/config.toml [audit] section.

    With --auto-archetype, AI selects the best archetype for generated topics.

    \b
    Examples:
        elmer daemon                                    # Start with defaults
        elmer daemon --interval 300                     # 5-minute cycles
        elmer daemon --auto-approve --generate          # Full autonomy
        elmer daemon --audit --auto-approve             # Audit mode
        elmer daemon --auto-archetype --generate        # AI picks archetypes
        elmer daemon --budget 5.00                      # Cost cap per cycle
        elmer daemon --max-concurrent 3                 # Limit parallelism
        elmer daemon status                             # Check daemon
        elmer daemon stop                               # Graceful shutdown
    """
    if ctx.invoked_subcommand is not None:
        return

    # Default: start the daemon
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    cfg = config.load_config(elmer_dir)
    d_cfg = cfg.get("daemon", {})
    fu_cfg = cfg.get("followup", {})
    audit_cfg = cfg.get("audit", {})

    try:
        daemon_mod.run_daemon(
            elmer_dir=elmer_dir,
            project_dir=project_dir,
            interval_seconds=interval or d_cfg.get("interval", 600),
            auto_approve=auto_approve or d_cfg.get("auto_approve", False),
            auto_generate=auto_generate or d_cfg.get("auto_generate", False),
            auto_archetype=auto_archetype or d_cfg.get("auto_archetype", False),
            budget_per_cycle=budget_per_cycle or d_cfg.get("budget_per_cycle"),
            max_concurrent=max_concurrent or d_cfg.get("max_concurrent", 5),
            generate_threshold=generate_threshold or d_cfg.get("generate_threshold", 2),
            generate_count=generate_count or d_cfg.get("generate_count", 5),
            auto_followup=auto_followup or fu_cfg.get("enabled", False),
            followup_count=followup_count or fu_cfg.get("count", 3),
            audit_enabled=audit_enabled or audit_cfg.get("enabled", False),
        )
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@daemon.command("status")
def daemon_status():
    """Check if the daemon is running."""
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    pid = daemon_mod.read_pidfile(elmer_dir)
    if pid:
        click.echo(f"Daemon running (PID {pid})")
    else:
        click.echo("Daemon not running.")


@daemon.command("stop")
def daemon_stop():
    """Stop the daemon gracefully.

    Sends SIGTERM, which lets the daemon finish its current cycle
    before shutting down.
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    pid = daemon_mod.read_pidfile(elmer_dir)
    if pid is None:
        click.echo("Daemon not running.")
        return

    import signal
    os.kill(pid, signal.SIGTERM)
    click.echo(f"Sent SIGTERM to daemon (PID {pid}). It will stop after the current cycle.")


@cli.command("mcp")
def mcp_cmd():
    """Start the MCP server for Claude Code integration.

    Exposes Elmer state as structured MCP tools over stdio JSON-RPC.
    Configure in Claude Code via .claude/mcp.json:

    \b
        {
          "mcpServers": {
            "elmer": {
              "command": "uv",
              "args": ["run", "elmer", "mcp"]
            }
          }
        }
    """
    from .mcp_server import main
    main()
