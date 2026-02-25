"""Daemon loop — continuous autonomous operation.

Composes existing primitives (harvest, gate, schedule, generate) into
a repeating cycle. The daemon runs in the foreground and uses signal
handlers for graceful shutdown.
"""

import logging
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from . import (
    autoapprove,
    config,
    digest as digest_mod,
    explore as explore_mod,
    gate,
    generate as gen_mod,
    implement as impl_mod,
    review,
    state,
    synthesize as synth_mod,
    worker,
)

logger = logging.getLogger("elmer.daemon")


class _DaemonState:
    """Mutable state shared across the daemon loop."""

    def __init__(self):
        self.should_stop = False
        self.cycle_count = 0
        self.total_cost = 0.0


# --- PID file management ---


def write_pidfile(elmer_dir: Path) -> Path:
    """Write daemon PID to .elmer/daemon.pid."""
    pidfile = elmer_dir / "daemon.pid"
    pidfile.write_text(str(os.getpid()))
    return pidfile


def read_pidfile(elmer_dir: Path) -> Optional[int]:
    """Read daemon PID. Returns None if not running."""
    pidfile = elmer_dir / "daemon.pid"
    if not pidfile.exists():
        return None
    try:
        pid = int(pidfile.read_text().strip())
        return pid if worker.is_running(pid) else None
    except (ValueError, OSError):
        return None


def remove_pidfile(elmer_dir: Path) -> None:
    """Remove daemon PID file."""
    pidfile = elmer_dir / "daemon.pid"
    if pidfile.exists():
        pidfile.unlink()


# --- Cycle cost tracking ---


def _get_cycle_cost(elmer_dir: Path, since: str) -> float:
    """Sum costs recorded since a timestamp. Best-effort."""
    conn = state.get_db(elmer_dir)
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0.0) FROM costs WHERE created_at >= ?",
        (since,),
    ).fetchone()
    meta_cost = row[0] if row else 0.0

    row2 = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0.0) FROM explorations "
        "WHERE completed_at >= ? AND cost_usd IS NOT NULL",
        (since,),
    ).fetchone()
    exp_cost = row2[0] if row2 else 0.0
    conn.close()
    return meta_cost + exp_cost


# --- Daemon log ---


def _log_cycle(
    elmer_dir: Path,
    cycle_number: int,
    started_at: str,
    harvested: int = 0,
    approved: int = 0,
    scheduled: int = 0,
    generated: int = 0,
    audits: int = 0,
    digests: int = 0,
    synthesized: int = 0,
    cycle_cost_usd: Optional[float] = None,
    error: Optional[str] = None,
) -> None:
    """Record a daemon cycle in the daemon_log table."""
    conn = state.get_db(elmer_dir)

    # Ensure columns exist (migration for existing DBs)
    for col in ["digests", "synthesized"]:
        try:
            conn.execute(f"ALTER TABLE daemon_log ADD COLUMN {col} INTEGER DEFAULT 0")
        except Exception:
            pass  # Column already exists

    conn.execute(
        """
        INSERT INTO daemon_log
            (cycle_number, started_at, completed_at, harvested, approved,
             scheduled, generated, audits, digests, synthesized, cycle_cost_usd, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (cycle_number, started_at, state._now(), harvested, approved,
         scheduled, generated, audits, digests, synthesized, cycle_cost_usd, error),
    )
    conn.commit()
    conn.close()


# --- Main loop ---


def run_daemon(
    *,
    elmer_dir: Path,
    project_dir: Path,
    interval_seconds: int = 600,
    auto_approve: bool = False,
    auto_generate: bool = False,
    auto_archetype: bool = False,
    budget_per_cycle: Optional[float] = None,
    max_concurrent: int = 5,
    generate_threshold: int = 2,
    generate_count: int = 5,
    auto_followup: bool = False,
    followup_count: int = 3,
    audit_enabled: bool = False,
) -> None:
    """Run the daemon loop until signalled to stop."""

    # Check for existing daemon
    existing_pid = read_pidfile(elmer_dir)
    if existing_pid is not None:
        raise RuntimeError(
            f"Daemon already running (PID {existing_pid}). "
            f"Use 'elmer daemon stop' first."
        )

    # Set up file logging
    log_path = elmer_dir / "logs" / "daemon.log"
    handler = logging.FileHandler(log_path)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    ds = _DaemonState()
    write_pidfile(elmer_dir)

    # Signal handlers for graceful shutdown
    def _handle_signal(signum, frame):
        logger.info("Received signal %d, finishing current cycle...", signum)
        ds.should_stop = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Load audit schedule from config
    audit_schedule: list[tuple[str, str]] = []
    if audit_enabled:
        cfg = config.load_config(elmer_dir)
        audit_cfg = cfg.get("audit", {})
        for entry in audit_cfg.get("schedule", []):
            if ":" in entry:
                arch, topic = entry.split(":", 1)
                audit_schedule.append((arch.strip(), topic.strip()))
            else:
                logger.warning("Invalid audit schedule entry (expected 'archetype:topic'): %s", entry)

    logger.info(
        "Daemon started (PID %d), interval %ds, auto_approve=%s, auto_generate=%s, audit=%s",
        os.getpid(), interval_seconds, auto_approve, auto_generate, audit_enabled,
    )
    click.echo(f"Daemon started (PID {os.getpid()}), interval {interval_seconds}s")
    click.echo(f"  Auto-approve: {auto_approve}")
    click.echo(f"  Auto-generate: {auto_generate}")
    click.echo(f"  Auto-archetype: {auto_archetype}")
    if audit_schedule:
        click.echo(f"  Audit schedule: {len(audit_schedule)} task(s)")
    if budget_per_cycle is not None:
        click.echo(f"  Budget/cycle: ${budget_per_cycle:.2f}")
    click.echo(f"  Max concurrent: {max_concurrent}")
    click.echo(f"  Log: {log_path}")
    click.echo()

    try:
        while not ds.should_stop:
            ds.cycle_count += 1
            cycle_start = state._now()
            logger.info("=== Cycle %d ===", ds.cycle_count)

            try:
                stats = _run_cycle(
                    elmer_dir=elmer_dir,
                    project_dir=project_dir,
                    ds=ds,
                    auto_approve=auto_approve,
                    auto_generate=auto_generate,
                    auto_archetype=auto_archetype,
                    budget_per_cycle=budget_per_cycle,
                    max_concurrent=max_concurrent,
                    generate_threshold=generate_threshold,
                    generate_count=generate_count,
                    auto_followup=auto_followup,
                    followup_count=followup_count,
                    cycle_start=cycle_start,
                    audit_schedule=audit_schedule,
                )
                cycle_cost = _get_cycle_cost(elmer_dir, cycle_start)
                _log_cycle(
                    elmer_dir,
                    cycle_number=ds.cycle_count,
                    started_at=cycle_start,
                    cycle_cost_usd=cycle_cost,
                    **stats,
                )
            except Exception as e:
                logger.error("Cycle %d failed: %s", ds.cycle_count, e)
                _log_cycle(
                    elmer_dir,
                    cycle_number=ds.cycle_count,
                    started_at=cycle_start,
                    error=str(e),
                )

            if ds.should_stop:
                break

            logger.info("Sleeping %ds until next cycle...", interval_seconds)
            # Sleep in small increments to check should_stop
            for _ in range(interval_seconds):
                if ds.should_stop:
                    break
                time.sleep(1)
    finally:
        remove_pidfile(elmer_dir)
        logger.info("Daemon stopped after %d cycle(s)", ds.cycle_count)
        click.echo(f"\nDaemon stopped after {ds.cycle_count} cycle(s).")


def _run_cycle(
    *,
    elmer_dir: Path,
    project_dir: Path,
    ds: _DaemonState,
    auto_approve: bool,
    auto_generate: bool,
    auto_archetype: bool = False,
    budget_per_cycle: Optional[float],
    max_concurrent: int,
    generate_threshold: int,
    generate_count: int,
    auto_followup: bool,
    followup_count: int,
    cycle_start: str,
    audit_schedule: Optional[list[tuple[str, str]]] = None,
) -> dict:
    """Execute one daemon cycle. Returns stats dict."""
    stats = {"harvested": 0, "approved": 0, "scheduled": 0, "generated": 0, "audits": 0, "digests": 0, "synthesized": 0}

    # Step 1: Harvest — check running PIDs, mark done/failed
    conn = state.get_db(elmer_dir)
    running_before = len(state.list_explorations(conn, status="running"))
    conn.close()

    review._refresh_running(elmer_dir, project_dir, notify=logger.info)

    conn = state.get_db(elmer_dir)
    running_after = len(state.list_explorations(conn, status="running"))
    conn.close()
    stats["harvested"] = max(0, running_before - running_after)
    if stats["harvested"]:
        logger.info("Harvested %d completed exploration(s)", stats["harvested"])

    # Step 1.5: Synthesize — trigger ensemble synthesis for ready ensembles
    # (Note: _refresh_running already triggers synthesis, but this catches any
    # that were missed or where the trigger failed on a previous cycle)
    try:
        synthesized = synth_mod.trigger_ready_ensembles(
            elmer_dir, project_dir, notify=logger.info,
        )
        stats["synthesized"] = len(synthesized)
        if synthesized:
            logger.info("Triggered %d ensemble synthesis(es)", len(synthesized))
    except Exception as e:
        logger.warning("Ensemble synthesis check failed: %s", e)

    # Step 2: Gate — auto-approve remaining done explorations
    # (_refresh_running already handles explorations flagged with auto_approve;
    # daemon-level auto_approve covers ALL done explorations)
    if auto_approve:
        conn = state.get_db(elmer_dir)
        done_exps = state.list_explorations(conn, status="done")
        conn.close()

        for exp in done_exps:
            if not exp["auto_approve"]:
                logger.info("Daemon auto-reviewing: %s", exp["id"])
                approved = autoapprove.evaluate(elmer_dir, project_dir, exp["id"])
                if approved:
                    logger.info("Daemon auto-approved: %s", exp["id"])
                    stats["approved"] += 1
                else:
                    logger.info("Queued for human review: %s", exp["id"])

    # Step 3: Follow-up — generate follow-ups for newly approved explorations
    if auto_followup:
        conn = state.get_db(elmer_dir)
        approved_exps = conn.execute(
            "SELECT * FROM explorations WHERE status = 'approved' AND merged_at >= ?",
            (cycle_start,),
        ).fetchall()
        conn.close()

        for exp in approved_exps:
            try:
                cfg = config.load_config(elmer_dir)
                fu_model = cfg.get("followup", {}).get("model", "sonnet")
                topics = gen_mod.generate_topics(
                    elmer_dir=elmer_dir,
                    project_dir=project_dir,
                    count=followup_count,
                    follow_up_id=exp["id"],
                    model=fu_model,
                )
                defaults = cfg.get("defaults", {})
                for topic in topics:
                    explore_mod.start_exploration(
                        topic=topic,
                        archetype=exp["archetype"],
                        model=exp["model"],
                        max_turns=exp["max_turns"] or defaults.get("max_turns", 50),
                        elmer_dir=elmer_dir,
                        project_dir=project_dir,
                        parent_id=exp["id"],
                        auto_approve=auto_approve,
                    )
                    stats["generated"] += 1
                logger.info("Generated %d follow-up(s) for %s", len(topics), exp["id"])
            except RuntimeError as e:
                logger.warning("Follow-up generation failed for %s: %s", exp["id"], e)

    # Step 4: Schedule — start unblocked pending explorations
    launched = explore_mod.schedule_ready(elmer_dir, project_dir)
    stats["scheduled"] = len(launched)
    for slug in launched:
        logger.info("Scheduled: %s", slug)

    # Step 5: Digest — synthesize if enough approvals have accumulated
    cfg = config.load_config(elmer_dir)
    digest_cfg = cfg.get("digest", {})
    digest_threshold = digest_cfg.get("threshold", 5)
    try:
        approvals_pending = digest_mod.approvals_since_last_digest(elmer_dir)
        if approvals_pending >= digest_threshold:
            logger.info(
                "Digest threshold reached (%d >= %d), synthesizing...",
                approvals_pending, digest_threshold,
            )
            digest_path = digest_mod.run_digest(
                elmer_dir=elmer_dir,
                project_dir=project_dir,
                model=digest_cfg.get("model", "sonnet"),
                max_turns=digest_cfg.get("max_turns", 5),
            )
            stats["digests"] = 1
            logger.info("Digest written: %s", digest_path)
    except Exception as e:
        logger.warning("Digest synthesis failed: %s", e)

    # Step 6: Check concurrency limit before generating or auditing
    conn = state.get_db(elmer_dir)
    running_count = conn.execute(
        "SELECT COUNT(*) FROM explorations WHERE status = 'running'"
    ).fetchone()[0]
    conn.close()

    if running_count >= max_concurrent:
        logger.info(
            "At concurrent limit (%d/%d), skipping generation and audits",
            running_count, max_concurrent,
        )
    else:
        # Step 6a: Audit — spawn next scheduled audit (one per cycle, rotating)
        if audit_schedule:
            audit_idx = (ds.cycle_count - 1) % len(audit_schedule)
            audit_arch, audit_topic = audit_schedule[audit_idx]
            logger.info(
                "Audit [%d/%d]: %s — %s",
                audit_idx + 1, len(audit_schedule),
                audit_arch, audit_topic or "(whole project)",
            )
            try:
                cfg = config.load_config(elmer_dir)
                audit_cfg = cfg.get("audit", {})
                defaults = cfg.get("defaults", {})
                slug, _ = explore_mod.start_exploration(
                    topic=audit_topic,
                    archetype=audit_arch,
                    model=audit_cfg.get("model", defaults.get("model", "sonnet")),
                    max_turns=audit_cfg.get("max_turns", defaults.get("max_turns", 50)),
                    elmer_dir=elmer_dir,
                    project_dir=project_dir,
                    auto_approve=audit_cfg.get("auto_approve", auto_approve),
                )
                stats["audits"] += 1
                logger.info("Audit started: %s (archetype: %s)", slug, audit_arch)
            except (RuntimeError, FileNotFoundError) as e:
                logger.warning("Audit failed for %s:%s — %s", audit_arch, audit_topic, e)

        # Step 6b: Generate — replenish if below threshold
        if auto_generate:
            conn = state.get_db(elmer_dir)
            active = conn.execute(
                "SELECT COUNT(*) FROM explorations WHERE status IN ('running', 'pending', 'done')"
            ).fetchone()[0]
            conn.close()

            if active < generate_threshold:
                logger.info(
                    "Active explorations (%d) below threshold (%d), generating topics",
                    active, generate_threshold,
                )
                try:
                    cfg = config.load_config(elmer_dir)
                    gen_cfg = cfg.get("generate", {})
                    defaults = cfg.get("defaults", {})
                    topics = gen_mod.generate_topics(
                        elmer_dir=elmer_dir,
                        project_dir=project_dir,
                        count=generate_count,
                        model=gen_cfg.get("model", defaults.get("model", "sonnet")),
                    )
                    for topic in topics:
                        explore_mod.start_exploration(
                            topic=topic,
                            archetype=defaults.get("archetype", "explore-act"),
                            model=defaults.get("model", "sonnet"),
                            max_turns=defaults.get("max_turns", 50),
                            elmer_dir=elmer_dir,
                            project_dir=project_dir,
                            auto_approve=auto_approve,
                            auto_archetype=auto_archetype,
                        )
                        stats["generated"] += 1
                    logger.info("Generated %d new topic(s)", len(topics))
                except RuntimeError as e:
                    logger.warning("Topic generation failed: %s", e)

    # Step 6c: Check implementation plan completion
    try:
        active_plans = impl_mod.get_plan_status(elmer_dir)
        for plan in active_plans:
            if plan["status"] == "completed":
                logger.info("Plan completed: %s (%s)", plan["id"], plan["milestone_ref"])
    except Exception as e:
        logger.warning("Plan status check failed: %s", e)

    # Step 7: Budget check
    if budget_per_cycle is not None:
        cycle_cost = _get_cycle_cost(elmer_dir, cycle_start)
        if cycle_cost >= budget_per_cycle:
            logger.info(
                "Cycle budget exceeded ($%.2f >= $%.2f), stopping",
                cycle_cost, budget_per_cycle,
            )
            ds.should_stop = True

    return stats
