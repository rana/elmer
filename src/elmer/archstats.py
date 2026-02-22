"""Archetype statistics — track which archetypes produce the best proposals."""

from pathlib import Path
from typing import Optional

import click

from . import state


def show_archetype_stats(elmer_dir: Path) -> None:
    """Display archetype effectiveness statistics."""
    conn = state.get_db(elmer_dir)
    explorations = state.list_explorations(conn)
    conn.close()

    if not explorations:
        click.echo("No explorations found.")
        return

    # Group explorations by archetype
    by_archetype: dict[str, list] = {}
    for exp in explorations:
        by_archetype.setdefault(exp["archetype"], []).append(exp)

    # Calculate stats per archetype
    stats = []
    for arch, exps in sorted(by_archetype.items()):
        total = len(exps)
        approved = sum(1 for e in exps if e["status"] == "approved")
        rejected = sum(1 for e in exps if e["status"] == "rejected")
        done = sum(1 for e in exps if e["status"] == "done")
        failed = sum(1 for e in exps if e["status"] == "failed")
        running = sum(1 for e in exps if e["status"] == "running")
        pending = sum(1 for e in exps if e["status"] == "pending")

        # Approval rate: approved / (approved + rejected), ignoring incomplete
        decided = approved + rejected
        approval_rate = (approved / decided * 100) if decided > 0 else None

        # Average cost (only for explorations with cost data)
        costs = [e["cost_usd"] for e in exps if e["cost_usd"] is not None]
        avg_cost = sum(costs) / len(costs) if costs else None

        # Follow-ups spawned (explorations with this one as parent)
        has_children = sum(1 for e in explorations if e["parent_id"] in
                          [x["id"] for x in exps])

        stats.append({
            "archetype": arch,
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "done": done,
            "failed": failed,
            "running": running,
            "pending": pending,
            "approval_rate": approval_rate,
            "avg_cost": avg_cost,
            "follow_ups": has_children,
        })

    # Sort by approval rate (best first), then by total count
    stats.sort(key=lambda s: (-(s["approval_rate"] or -1), -s["total"]))

    # Display
    click.echo(
        f"{'ARCHETYPE':<22} {'TOTAL':>5} {'APPR':>5} {'REJ':>5} "
        f"{'DONE':>5} {'FAIL':>5} {'RATE':>7} {'AVG COST':>9}"
    )
    click.echo("-" * 72)

    for s in stats:
        rate = f"{s['approval_rate']:.0f}%" if s['approval_rate'] is not None else "-"
        cost = f"${s['avg_cost']:.2f}" if s['avg_cost'] is not None else "-"
        click.echo(
            f"{s['archetype']:<22} {s['total']:>5} {s['approved']:>5} "
            f"{s['rejected']:>5} {s['done']:>5} {s['failed']:>5} "
            f"{rate:>7} {cost:>9}"
        )

    click.echo()
    total_all = sum(s["total"] for s in stats)
    approved_all = sum(s["approved"] for s in stats)
    rejected_all = sum(s["rejected"] for s in stats)
    decided_all = approved_all + rejected_all
    rate_all = f"{approved_all / decided_all * 100:.0f}%" if decided_all > 0 else "-"
    click.echo(
        f"{total_all} exploration(s) across {len(stats)} archetype(s). "
        f"Overall approval rate: {rate_all}"
    )

    # Recommendations
    if len(stats) >= 2 and any(s["approval_rate"] is not None for s in stats):
        best = next((s for s in stats if s["approval_rate"] is not None), None)
        if best and best["approval_rate"] is not None and best["total"] >= 3:
            click.echo(
                f"\nTop performer: {best['archetype']} "
                f"({best['approval_rate']:.0f}% approval, {best['total']} explorations)"
            )
