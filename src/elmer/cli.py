"""Elmer CLI — Autonomous research with branching."""

import sys
from pathlib import Path

import click

from . import config, explore as explore_mod, gate, review as review_mod, worktree as wt


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
    return elmer_dir


# --- Commands ---


@cli.command()
def init():
    """Initialize Elmer in the current project."""
    project_dir = _require_project()
    elmer_dir = config.init_project(project_dir)
    click.echo(f"Initialized .elmer/ in {project_dir}")
    click.echo(f"  Config:     {elmer_dir / 'config.toml'}")
    click.echo(f"  Archetypes: {elmer_dir / 'archetypes/'}")
    click.echo()
    click.echo("Edit .elmer/config.toml to change defaults.")
    click.echo("Add custom archetypes to .elmer/archetypes/.")


@cli.command()
@click.argument("topic", required=False)
@click.option("-a", "--archetype", default=None, help="Archetype template (default: from config)")
@click.option("-m", "--model", default=None, help="Model: sonnet, opus, haiku (default: from config)")
@click.option("-f", "--file", "topics_file", type=click.Path(exists=True), help="File with one topic per line")
@click.option("--max-turns", default=None, type=int, help="Max turns for claude session")
def explore(topic, archetype, model, topics_file, max_turns):
    """Start an exploration on a new branch.

    Each exploration gets its own git worktree and a background Claude
    session that writes a PROPOSAL.md when done.

    \b
    Examples:
        elmer explore "evaluate COT positioning data"
        elmer explore "prototype search API" -a prototype -m opus
        elmer explore -f topics.txt
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    if not topic and not topics_file:
        click.echo("Error: provide a topic or --file.", err=True)
        sys.exit(1)

    cfg = config.load_config(elmer_dir)
    defaults = cfg.get("defaults", {})
    archetype = archetype or defaults.get("archetype", "explore-act")
    model = model or defaults.get("model", "sonnet")
    max_turns = max_turns or defaults.get("max_turns", 50)

    # Collect topics
    topics: list[str] = []
    if topics_file:
        with open(topics_file) as f:
            topics = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    if topic:
        topics.append(topic)

    for t in topics:
        try:
            slug = explore_mod.start_exploration(
                topic=t,
                archetype=archetype,
                model=model,
                max_turns=max_turns,
                elmer_dir=elmer_dir,
                project_dir=project_dir,
            )
            click.echo(f"Started: {slug}")
            click.echo(f"  Branch:    elmer/{slug}")
            click.echo(f"  Archetype: {archetype}")
            click.echo(f"  Model:     {model}")
            click.echo(f"  Log:       .elmer/logs/{slug}.log")
            click.echo()
        except (RuntimeError, FileNotFoundError) as e:
            click.echo(f"Error: {e}", err=True)


@cli.command()
def status():
    """Show exploration status."""
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)
    review_mod.show_status(elmer_dir)


@cli.command()
@click.argument("exploration_id", required=False)
def review(exploration_id):
    """Review exploration proposals.

    Without an ID, lists all proposals pending review.
    With an ID, shows the full proposal content.
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    if exploration_id:
        review_mod.show_proposal(elmer_dir, exploration_id)
    else:
        review_mod.list_proposals(elmer_dir)


@cli.command()
@click.argument("exploration_id", required=False)
@click.option("--all", "approve_all_flag", is_flag=True, help="Approve all pending proposals")
def approve(exploration_id, approve_all_flag):
    """Approve and merge an exploration.

    Merges the exploration branch into the current branch and cleans up
    the worktree.
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    if approve_all_flag:
        approved = gate.approve_all(elmer_dir, project_dir)
        if approved:
            click.echo(f"Approved {len(approved)} exploration(s): {', '.join(approved)}")
        else:
            click.echo("No proposals pending approval.")
        return

    if not exploration_id:
        click.echo("Error: provide an exploration ID or --all.", err=True)
        sys.exit(1)

    gate.approve_exploration(elmer_dir, project_dir, exploration_id)
    click.echo(f"Approved and merged: {exploration_id}")


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
def clean():
    """Clean up finished explorations.

    Removes worktrees and state entries for approved and rejected
    explorations. Running and pending explorations are not affected.
    """
    project_dir = _require_project()
    elmer_dir = _require_elmer(project_dir)

    count = gate.clean_all(elmer_dir, project_dir)
    click.echo(f"Cleaned {count} exploration(s).")
