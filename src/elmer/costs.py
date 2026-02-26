"""Cost reporting — display token usage and cost summaries."""

from pathlib import Path
from typing import Optional

import click

from . import config, state


def _fmt_tokens(n: Optional[int]) -> str:
    """Format token count with comma separators, or '-' if None."""
    if n is None:
        return "-"
    return f"{n:,}"


def _fmt_cost(c: Optional[float]) -> str:
    """Format cost as $X.XX, or '-' if None."""
    if c is None:
        return "-"
    return f"${c:.2f}"


def show_costs(elmer_dir: Path, exploration_id: Optional[str] = None) -> None:
    """Display cost summary."""
    conn = state.get_db(elmer_dir)

    if exploration_id:
        _show_single(conn, exploration_id)
    else:
        _show_summary(conn)

    conn.close()


def _show_single(conn, exploration_id: str) -> None:
    """Show cost details for a single exploration."""
    exp = state.get_exploration(conn, exploration_id)
    if exp is None:
        click.echo(f"Exploration '{exploration_id}' not found.", err=True)
        return

    click.echo(f"Exploration: {exp['id']}")
    click.echo(f"  Model:        {exp['model']}")
    click.echo(f"  Status:       {exp['status']}")
    click.echo(f"  Input tokens: {_fmt_tokens(exp['input_tokens'])}")
    click.echo(f"  Output tokens:{_fmt_tokens(exp['output_tokens'])}")
    click.echo(f"  Cost:         {_fmt_cost(exp['cost_usd'])}")
    click.echo(f"  Turns used:   {exp['num_turns_actual'] or '-'}")
    # Show linked meta-operation costs
    meta_costs = conn.execute(
        "SELECT * FROM costs WHERE exploration_id = ? ORDER BY created_at",
        (exploration_id,),
    ).fetchall()

    if meta_costs:
        click.echo()
        click.echo("  Meta-operations:")
        for mc in meta_costs:
            click.echo(
                f"    {mc['operation']:<14} {mc['model']:<8} {_fmt_cost(mc['cost_usd'])}"
            )


def _show_summary(conn) -> None:
    """Show cost summary for all explorations and meta-operations."""
    explorations = state.list_explorations(conn)
    meta_costs = state.get_all_costs(conn)

    has_any_costs = False

    # --- Explorations ---
    exps_with_costs = [e for e in explorations if e["cost_usd"] is not None]

    if exps_with_costs:
        has_any_costs = True
        click.echo("Explorations:")
        click.echo(
            f"  {'ID':<30} {'MODEL':<8} {'TOKENS IN':>10} {'TOKENS OUT':>11} "
            f"{'COST':>8} {'STATUS':<10}"
        )
        click.echo(f"  {'-' * 79}")

        total_exp_cost = 0.0
        for exp in exps_with_costs:
            cost = exp["cost_usd"] or 0.0
            total_exp_cost += cost
            eid = exp["id"]
            if len(eid) > 28:
                eid = eid[:27] + ".."
            click.echo(
                f"  {eid:<30} {exp['model']:<8} "
                f"{_fmt_tokens(exp['input_tokens']):>10} "
                f"{_fmt_tokens(exp['output_tokens']):>11} "
                f"{_fmt_cost(exp['cost_usd']):>8} {exp['status']:<10}"
            )

        click.echo(
            f"  {'':>50} {'--------':>8}"
        )
        click.echo(
            f"  {len(exps_with_costs)} exploration(s){' ' * 36}"
            f"{_fmt_cost(total_exp_cost):>8}"
        )
        click.echo()

    # --- Meta-operations ---
    if meta_costs:
        has_any_costs = True
        click.echo("Meta-Operations:")

        # Group by operation + model
        groups: dict[tuple[str, str], list] = {}
        for mc in meta_costs:
            key = (mc["operation"], mc["model"])
            groups.setdefault(key, []).append(mc)

        total_meta_cost = 0.0
        for (op, model), items in sorted(groups.items()):
            group_cost = sum(m["cost_usd"] or 0.0 for m in items)
            total_meta_cost += group_cost
            click.echo(
                f"  {op} ({model}): {len(items)} call(s), {_fmt_cost(group_cost)}"
            )

        click.echo(f"  Total meta-operations: {_fmt_cost(total_meta_cost)}")
        click.echo()

    # --- Totals ---
    if has_any_costs:
        exp_total = sum(e["cost_usd"] or 0.0 for e in exps_with_costs)
        meta_total = sum(m["cost_usd"] or 0.0 for m in meta_costs)
        click.echo(
            f"Total: {_fmt_cost(exp_total + meta_total)}  "
            f"({len(exps_with_costs)} exploration(s), {len(meta_costs)} meta-op(s))"
        )
    else:
        # Check if there are any explorations at all
        if explorations:
            click.echo("No cost data recorded yet.")
            click.echo("Costs are extracted from claude session output when explorations complete.")
        else:
            click.echo("No explorations found. Run 'elmer explore \"topic\"' to start one.")
