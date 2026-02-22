"""Multi-project dashboard — aggregate status across all registered projects."""

from pathlib import Path

import click

from . import config, state


def show_all_projects() -> None:
    """Display status summary across all registered Elmer projects."""
    projects = config.list_registered_projects()

    if not projects:
        click.echo("No registered projects found.")
        click.echo("Run 'elmer init' in your projects to register them.")
        return

    click.echo(f"{'PROJECT':<30} {'RUN':>4} {'DONE':>5} {'PEND':>5} {'APPR':>5} {'REJ':>5} {'FAIL':>5} {'TOTAL':>6} {'COST':>10}")
    click.echo("-" * 90)

    grand_totals = {"running": 0, "done": 0, "pending": 0, "approved": 0,
                    "rejected": 0, "failed": 0, "total": 0, "cost": 0.0}

    for project_dir in projects:
        elmer_dir = project_dir / ".elmer"
        name = project_dir.name
        if len(name) > 28:
            name = name[:27] + ".."

        try:
            conn = state.get_db(elmer_dir)
            explorations = state.list_explorations(conn)
            conn.close()
        except Exception:
            click.echo(f"{name:<30} (error reading state)")
            continue

        counts = {"running": 0, "done": 0, "pending": 0, "approved": 0,
                  "rejected": 0, "failed": 0}
        total_cost = 0.0

        for exp in explorations:
            s = exp["status"]
            if s in counts:
                counts[s] += 1
            cost = exp["cost_usd"]
            if cost:
                total_cost += cost

        total = len(explorations)

        click.echo(
            f"{name:<30} {counts['running']:>4} {counts['done']:>5} "
            f"{counts['pending']:>5} {counts['approved']:>5} {counts['rejected']:>5} "
            f"{counts['failed']:>5} {total:>6} "
            f"{'$' + f'{total_cost:.2f}':>10}"
        )

        for k in counts:
            grand_totals[k] += counts[k]
        grand_totals["total"] += total
        grand_totals["cost"] += total_cost

    if len(projects) > 1:
        click.echo("-" * 90)
        cost_str = "$" + f"{grand_totals['cost']:.2f}"
        click.echo(
            f"{'TOTAL':<30} {grand_totals['running']:>4} {grand_totals['done']:>5} "
            f"{grand_totals['pending']:>5} {grand_totals['approved']:>5} "
            f"{grand_totals['rejected']:>5} {grand_totals['failed']:>5} "
            f"{grand_totals['total']:>6} "
            f"{cost_str:>10}"
        )

    click.echo(f"\n{len(projects)} project(s) registered.")
