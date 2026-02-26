"""Archetype statistics — track which archetypes produce the best proposals."""

from pathlib import Path
from typing import Optional

import click

from . import digest as digest_mod, state


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
        declined = sum(1 for e in exps if e["status"] == "declined")
        done = sum(1 for e in exps if e["status"] == "done")
        failed = sum(1 for e in exps if e["status"] == "failed")
        running = sum(1 for e in exps if e["status"] == "running")
        pending = sum(1 for e in exps if e["status"] == "pending")

        # Approval rate: approved / (approved + declined), ignoring incomplete
        decided = approved + declined
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
            "declined": declined,
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
        f"{'ARCHETYPE':<22} {'TOTAL':>5} {'APPR':>5} {'DECL':>5} "
        f"{'DONE':>5} {'FAIL':>5} {'RATE':>7} {'AVG COST':>9}"
    )
    click.echo("-" * 72)

    for s in stats:
        rate = f"{s['approval_rate']:.0f}%" if s['approval_rate'] is not None else "-"
        cost = f"${s['avg_cost']:.2f}" if s['avg_cost'] is not None else "-"
        click.echo(
            f"{s['archetype']:<22} {s['total']:>5} {s['approved']:>5} "
            f"{s['declined']:>5} {s['done']:>5} {s['failed']:>5} "
            f"{rate:>7} {cost:>9}"
        )

    click.echo()
    total_all = sum(s["total"] for s in stats)
    approved_all = sum(s["approved"] for s in stats)
    declined_all = sum(s["declined"] for s in stats)
    decided_all = approved_all + declined_all
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


def diagnose_archetype(elmer_dir: Path, archetype_name: str) -> dict:
    """Diagnose an archetype's effectiveness across explorations (I1).

    Reads approval/decline rates, decline reasons, verification failure
    counts, topic patterns, and average turns. Returns a structured report
    dict and also displays it via click.echo.

    This is read-only — it never modifies agent definitions.
    """
    conn = state.get_db(elmer_dir)
    all_explorations = state.list_explorations(conn)
    conn.close()

    # Also load archive for completed explorations
    archived = digest_mod._load_archived_proposals(elmer_dir)

    # Filter to this archetype
    db_exps = [e for e in all_explorations if e["archetype"] == archetype_name]
    arch_archived = [m for m in archived if m.get("archetype") == archetype_name]

    # Merge: use DB as primary, archive fills gaps
    seen_ids = {e["id"] for e in db_exps}
    total_count = len(db_exps)

    approved = [e for e in db_exps if e["status"] == "approved"]
    declined = [e for e in db_exps if e["status"] == "declined"]
    failed = [e for e in db_exps if e["status"] == "failed"]

    # Add archive data for cleaned records
    for meta in arch_archived:
        if meta.get("id") in seen_ids:
            continue
        total_count += 1
        if meta.get("status") == "approved":
            approved.append(meta)
        elif meta.get("status") == "declined":
            declined.append(meta)

    decided = len(approved) + len(declined)
    approval_rate = (len(approved) / decided * 100) if decided > 0 else None

    # Decline reasons
    decline_reasons = []
    for e in declined:
        reason = ""
        try:
            reason = e.get("decline_reason") or e["decline_reason"] or ""
        except (KeyError, TypeError):
            pass
        if reason:
            decline_reasons.append(reason)

    # Verification failures (from DB only)
    total_verify_failures = 0
    for e in db_exps:
        try:
            vf = e["verification_failures"] or 0
            total_verify_failures += vf
        except (KeyError, TypeError):
            pass

    # Topic patterns: what topics succeed vs fail
    approved_topics = []
    for e in approved:
        topic = e.get("topic", e.get("id", ""))
        if isinstance(topic, str) and topic:
            approved_topics.append(topic)

    declined_topics = []
    for e in declined:
        topic = e.get("topic", e.get("id", ""))
        if isinstance(topic, str) and topic:
            declined_topics.append(topic)

    failed_topics = []
    for e in failed:
        topic = e["topic"] if isinstance(e, dict) or hasattr(e, "keys") else ""
        try:
            topic = e["topic"]
        except (KeyError, TypeError):
            pass
        if topic:
            failed_topics.append(topic)

    # Average turns used (from DB only)
    turns_list = []
    for e in db_exps:
        try:
            turns = e["num_turns_actual"]
            if turns is not None:
                turns_list.append(turns)
        except (KeyError, TypeError):
            pass
    avg_turns = sum(turns_list) / len(turns_list) if turns_list else None

    # Build report
    report = {
        "archetype": archetype_name,
        "total_explorations": total_count,
        "approved": len(approved),
        "declined": len(declined),
        "failed": len(failed),
        "approval_rate": approval_rate,
        "decline_reasons": decline_reasons,
        "verification_failures": total_verify_failures,
        "avg_turns": avg_turns,
        "approved_topics": approved_topics[:10],
        "declined_topics": declined_topics[:10],
        "failed_topics": failed_topics[:10],
    }

    # Display
    click.echo(f"\nArchetype Diagnosis: {archetype_name}")
    click.echo("=" * 50)
    click.echo(f"Total explorations: {total_count}")
    click.echo(f"Approved:           {len(approved)}")
    click.echo(f"Declined:           {len(declined)}")
    click.echo(f"Failed:             {len(failed)}")
    if approval_rate is not None:
        click.echo(f"Approval rate:      {approval_rate:.0f}%")
    if avg_turns is not None:
        click.echo(f"Avg turns used:     {avg_turns:.1f}")
    click.echo(f"Verify failures:    {total_verify_failures}")

    if decline_reasons:
        click.echo(f"\nDecline Reasons ({len(decline_reasons)}):")
        for reason in decline_reasons[:5]:
            click.echo(f"  - {reason[:120]}")
        if len(decline_reasons) > 5:
            click.echo(f"  ... and {len(decline_reasons) - 5} more")

    if approved_topics:
        click.echo(f"\nSuccessful Topics ({len(approved_topics)}):")
        for topic in approved_topics[:5]:
            click.echo(f"  + {topic[:100]}")

    if declined_topics:
        click.echo(f"\nDeclined Topics ({len(declined_topics)}):")
        for topic in declined_topics[:5]:
            click.echo(f"  - {topic[:100]}")

    if failed_topics:
        click.echo(f"\nFailed Topics ({len(failed_topics)}):")
        for topic in failed_topics[:5]:
            click.echo(f"  ! {topic[:100]}")

    # Diagnostic summary
    click.echo(f"\nDiagnosis:")
    if total_count < 3:
        click.echo(f"  Insufficient data ({total_count} explorations). Need >= 3 for meaningful diagnosis.")
    elif approval_rate is not None and approval_rate < 30:
        click.echo(f"  LOW APPROVAL RATE ({approval_rate:.0f}%). This archetype may not suit the project's needs.")
        if decline_reasons:
            click.echo(f"  Most common decline reason may indicate a systematic methodology issue.")
    elif approval_rate is not None and approval_rate >= 80:
        click.echo(f"  HIGH APPROVAL RATE ({approval_rate:.0f}%). This archetype is well-suited to its tasks.")
    elif approval_rate is not None:
        click.echo(f"  MODERATE APPROVAL RATE ({approval_rate:.0f}%). Review decline reasons for improvement opportunities.")

    if total_verify_failures > len(db_exps) * 0.5:
        click.echo(f"  HIGH VERIFICATION FAILURE RATE. The archetype may need stronger self-verification instructions.")

    return report
