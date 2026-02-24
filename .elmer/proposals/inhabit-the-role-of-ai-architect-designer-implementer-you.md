<!-- elmer:archive
  id: inhabit-the-role-of-ai-architect-designer-implementer-you
  topic: Inhabit the role of AI architect, designer, implementer. You consider using the elmer MCP server. What do you see for, against, and through? What would you use and not use? Generatively imagine what you wish elmer MCP offered? What would benefit you?
  archetype: explore-act
  model: sonnet
  status: approved
  archived: 2026-02-24 07:19 UTC
-->

## Summary

From the perspective of an AI architect/designer/implementer using Claude Code, the Elmer MCP server is structurally well-designed but has significant gaps in compositional intelligence, real-time feedback, and integration depth. I would use it for state queries and batch operations but avoid it for interactive design work. The missing pieces: streaming status, partial result recovery, exploration session introspection, and compositional tool chaining. What I wish it offered: the ability to observe and steer running explorations, not just spawn-and-wait.

## Analysis

### What Works (For Me)

**1. Structured state access eliminates parsing hell.** The MCP server solves the real problem: CLI table parsing is brittle. `elmer_status()` returns JSON with exploration state, costs, dependencies — I can reason about this natively. No regex. No "extract the ID from column 2." This is table stakes for AI tool use, and Elmer gets it right.

**2. Mutation tools match my mental model.** `elmer_explore()`, `elmer_approve()`, `elmer_decline()` map cleanly to the core operations. The parameter surface is sensible: I can pass `auto_approve`, `budget_usd`, `depends_on` without CLI flag archaeology. Error responses are structured (`{"error": "..."}`) rather than exit codes.

**3. Intelligence tools enable discovery.** `elmer_generate()` with `spawn=false` gives me topics to consider before committing. `elmer_mine_questions()` surfaces gaps I wouldn't have found manually. `elmer_digest()` with filters lets me synthesize domain-specific convergence. These are compositional primitives — I can call them, reason about results, then decide whether to spawn.

**4. The read-only tools are complete.** `elmer_review(prioritize=true)` gives me ranked proposals with reasons. `elmer_tree()` shows dependency structure. `elmer_costs()` aggregates spend. `elmer_archetypes(include_stats=true)` shows approval rates. No information is trapped in the CLI — everything I need to make decisions is exposed.

### What Doesn't Work (For Me)

**1. No streaming status — spawned explorations are black boxes.** I call `elmer_explore()`, get back `{"id": "...", "status": "running"}`, and then... nothing. I can poll `elmer_status()` to check if it's still running, but I can't see *what it's doing*. Is it reading docs? Running bash commands? Stuck in a loop? Has it written 80% of PROPOSAL.md? The session log exists (`.elmer/logs/<id>.log`), but there's no tool to stream or tail it. I'm blind until it finishes or fails.

**Use case I can't do:** "Show me what the currently running explorations are working on." I'd want to call something like `elmer_session_activity(exploration_id)` and get back recent tool calls, file reads, command executions — enough to understand progress without the full log dump.

**2. No partial result recovery.** If an exploration fails (wrong PROPOSAL.md path, exceeded turns, permission denials), the entire session is lost. The failure diagnostics in `elmer_logs()` are post-mortem only. I can see *why* it failed, but I can't see *what it produced before failing*. Maybe it wrote 90% of a great analysis but crashed on the final Write. There's no way to salvage partial work.

**Use case I can't do:** "This exploration failed after 45 turns — show me any markdown it drafted in memory or in temp files." I'd want `elmer_recover_partial(exploration_id)` to scrape the worktree for any `.md` files, claude session artifacts, or partial outputs.

**3. No exploration introspection beyond status.** `elmer_status()` tells me an exploration is "running" or "done", but not *how far through the methodology* it is. Exploration agents have structure (read docs → analyze → propose → write), but the MCP has no visibility into which phase is active. I can't tell if "running" means "still reading DESIGN.md" or "finalizing the 5th revision of PROPOSAL.md."

**Use case I can't do:** "Is this exploration making progress or stuck?" Without turn count, active file, or recent tool activity, I can't distinguish productive work from a hung process.

**4. No compositional chaining between tools.** Each MCP tool is atomic. To implement a workflow like "generate topics → filter by keyword → spawn the top 3 → monitor until first completion → review it," I have to orchestrate 5+ sequential tool calls myself. The MCP has no equivalent of Elmer's `--on-approve` chain actions or `--auto-followup`.

**Use case I can't do:** "If any of these 3 explorations approve, automatically spawn a follow-up that synthesizes them." The MCP would need something like `elmer_watch(exploration_ids, on_approve=<callback spec>)`, but callbacks aren't in the MCP model.

**5. Batch operations lack stagger/throttle control.** `elmer_batch()` accepts `max_concurrent`, but there's no stagger parameter (delay between spawns) or cost velocity controls (max spend per hour). If I spawn 20 explorations with opus, they all start immediately (up to max_concurrent), potentially hitting API rate limits or budget burn faster than intended.

**Use case I can't do:** "Spawn these 10 topics but stagger starts by 2 minutes each to avoid rate limits." The CLI has `--stagger`, but the MCP doesn't expose it.

**6. No digest/generate integration observability.** `elmer_generate()` says it's "digest-aware" — it reads the latest digest. But the tool doesn't return *which* digest it used, when it was created, or how many explorations it synthesized. I'm trusting that the generation is informed by recent convergence, but I can't verify it or debug stale digest issues.

**Use case I can't do:** "Show me which digest informed this topic generation and its timestamp." I'd want `elmer_generate()` to return `{"topics": [...], "digest_used": {"path": "...", "timestamp": "...", "approval_count": 12}}`.

**7. Amendment doesn't expose the amending agent's prompt.** `elmer_amend()` takes feedback and spawns a revision session. But I don't see the actual prompt given to the amend agent — I'm trusting that my feedback was interpreted correctly. If the amendment produces something unexpected, I have no way to inspect *what instructions the agent actually received*.

**Use case I can't do:** "Before amending, show me the prompt that will be sent to the amend agent." I'd want `elmer_amend(..., dry_run=true)` to return the assembled prompt without spawning the session.

**8. Validation runs but doesn't show fixes before applying.** `elmer_validate()` auto-fixes mechanical violations (ADR counts, status labels). The response includes `"fixes": [...]`, but only *after* the files are already modified. There's no preview mode. If I want to review fixes before approving, I have to call validate, inspect the response, then manually revert or accept.

**Use case I can't do:** "Show me what elmer validate would fix without changing files." I'd want `elmer_validate(preview=true)` to return proposed fixes as diffs, then `elmer_validate(apply=true)` to commit them.

**9. The PR tool is fire-and-forget.** `elmer_pr()` pushes the branch and creates a PR, but returns only `{"pr_url": "..."}`. No indication of what was pushed, how many commits, whether gh CLI used cached credentials or prompted (which would block), or whether the PR body was truncated (GitHub has limits). If it succeeds, great. If it fails, the error is a generic exception string.

**Use case I can't do:** "Before creating a PR, show me the commit log and the proposed PR body." I'd want `elmer_pr(..., preview=true)` to return the commits, diff stat, and formatted PR body without pushing.

**10. No way to inspect or modify config via MCP.** The MCP reads `.elmer/config.toml` (via `config.load_config()`), but there's no tool to view or update it. If I want to check the default archetype, auto-approve criteria, or digest threshold, I have to use the Bash tool to read the file. If I want to change a setting, I have to edit TOML manually.

**Use case I can't do:** "Show me the current auto-approve criteria." I'd want `elmer_config_get("approve_criteria")` and `elmer_config_set("approve_criteria", {...})`.

### What I Would Not Use (And Why)

**1. `elmer_clean()` without confirmation.** It removes all finished worktrees and state entries. In a large project with many approved explorations, this could delete valuable branch history before I've had a chance to extract insights or review the archive. The tool has no preview mode, no `--dry-run`, no undo. It's too destructive for casual use.

**When I'd use it:** Only after manually verifying `elmer_status()` shows no explorations I care about preserving, and after confirming `.elmer/proposals/` has archives.

**2. `elmer_approve(approve_all=true)` in interactive sessions.** Batch approval is useful for the daemon, but dangerous in an interactive session where I haven't reviewed each proposal. If one exploration has a merge conflict, `approve_all` aborts that one and continues — I might not notice which ones succeeded vs. which were skipped.

**When I'd use it:** Only when I've already called `elmer_review(prioritize=true)`, read every proposal, and consciously decided they're all safe to merge.

**3. `elmer_generate(spawn=true)` with defaults.** Generating *and* spawning topics in one call is convenient but risky. If generation produces 5 topics and I disagree with 3 of them, I've already committed compute budget to spawning them. I'd rather generate, review, filter, then spawn explicitly.

**When I'd use it:** Only with `spawn=false` first, then explicit `elmer_explore()` calls for topics I approve.

**4. `elmer_batch()` with `chain=true` on unknown topics.** Chaining makes topics depend on each other sequentially. If topic 2 depends on topic 1, and topic 1 fails or gets declined, the entire chain stalls. For exploratory work where I don't know if the approach will succeed, chaining is premature optimization.

**When I'd use it:** Only for refactoring workflows where I know the sequence is correct (e.g., "rename X, then update callers, then update tests" — these *must* be sequential).

**5. `elmer_retry(retry_all_failed=true)` without inspecting failure reasons first.** If 10 explorations failed, retrying them all immediately might repeat the same systemic issue (wrong archetype, insufficient turns, budget too low). I'd want to inspect `elmer_logs()` for each failed ID, understand the root cause, then retry selectively or with adjusted parameters.

**When I'd use it:** After manually reviewing logs and confirming the failures were transient (API errors, rate limits) rather than configuration issues.

## Proposed Changes

### 1. Add Session Activity Introspection

**What:** New MCP tool `elmer_session_activity(exploration_id, lines=20)` that returns recent activity from a running/amending exploration's session log.

**Where:**
- New function in `mcp_server.py` (read-only tool group)
- Reuses `worker.parse_session_log()` but operates on incomplete logs
- Returns structured JSON: `{"turns": [...], "recent_tools": [...], "files_accessed": [...], "status": "active|idle|completing"}`

**Why:** Currently, running explorations are black boxes. This gives real-time visibility into what a session is doing without waiting for completion. Enables progress monitoring and early cancellation of stuck sessions.

**How:**
```python
@mcp.tool()
def elmer_session_activity(exploration_id: str, lines: int = 20) -> dict:
    """Real-time activity view for running/amending explorations."""
    # Read last N lines of .elmer/logs/<id>.log
    # Parse JSON objects for tool calls, file access, turn markers
    # Return structured summary with timestamp
    # Handle incomplete logs gracefully (partial JSON)
```

### 2. Add Partial Result Recovery

**What:** New MCP tool `elmer_recover_partial(exploration_id)` that scrapes the worktree for any artifacts created before failure.

**Where:**
- New function in `mcp_server.py` (read-only tool group)
- Searches worktree for `*.md` files, draft output, anything resembling proposal content
- Returns file paths and previews of content found

**Why:** Failed explorations often produce valuable partial work. Current behavior discards everything. This allows salvaging partial proposals, analysis fragments, or diagnostic output.

**How:**
```python
@mcp.tool()
def elmer_recover_partial(exploration_id: str) -> dict:
    """Recover partial artifacts from failed exploration."""
    # Get worktree path from DB
    # Glob for *.md files (excluding standard project docs)
    # Read and return content previews (first 500 chars each)
    # Include timestamps to show writing sequence
```

### 3. Enhance Status with Progress Indicators

**What:** Extend `elmer_status()` to include progress indicators for running explorations: turn count, active file, time since last activity.

**Where:**
- Modify `elmer_status()` in `mcp_server.py`
- Parse session logs for running/amending explorations to extract turn count and last activity timestamp
- Add fields: `"turn_count": N`, `"last_activity": "2026-02-23T10:30:00Z"`, `"active_file": "DESIGN.md"`

**Why:** "Running" tells me nothing about progress. Turn count shows if it's approaching max_turns. Last activity timestamp reveals if it's hung. Active file shows which phase of methodology it's in.

**How:**
```python
# In elmer_status(), for running/amending explorations:
if exp["status"] in ("running", "amending"):
    activity = _parse_recent_activity(exp["id"])  # helper function
    result["turn_count"] = activity.get("turn_count")
    result["last_activity"] = activity.get("timestamp")
    result["active_file"] = activity.get("current_file")
```

### 4. Add Preview Mode for Destructive Operations

**What:** Add `preview` parameter to `elmer_validate()`, `elmer_clean()`, and `elmer_pr()` to show what would happen without executing.

**Where:**
- Modify existing tools in `mcp_server.py` to accept `preview: bool = False`
- For validate: return proposed fixes as diffs without applying
- For clean: return list of worktrees/state entries that would be removed
- For pr: return commit log, diff stat, and formatted PR body without pushing

**Why:** Destructive operations should be inspectable before execution. Preview enables review-then-confirm workflow.

**How:**
```python
@mcp.tool()
def elmer_validate(model: Optional[str] = None, preview: bool = False) -> dict:
    if preview:
        # Run validation, collect fixes, return without applying
        return {"fixes": [...], "preview": True}
    # Existing behavior
```

### 5. Add Config Introspection Tools

**What:** New MCP tools `elmer_config_get(key=None)` and `elmer_config_set(key, value)` for reading and modifying `.elmer/config.toml`.

**Where:**
- New functions in `mcp_server.py` (config tool group)
- Uses `tomli`/`tomli_w` for parsing/writing TOML
- Validates key paths (e.g., "defaults.archetype", "approve_criteria")

**Why:** Config is currently file-only access. AI agents should be able to query and adjust settings programmatically (e.g., increase default max_turns, modify auto-approve criteria, change digest threshold).

**How:**
```python
@mcp.tool()
def elmer_config_get(key: Optional[str] = None) -> dict:
    """Get config values. Without key, returns full config."""
    cfg = config.load_config(elmer_dir)
    if key:
        # Navigate nested dict: "defaults.model" -> cfg["defaults"]["model"]
        return {"key": key, "value": ...}
    return {"config": cfg}

@mcp.tool()
def elmer_config_set(key: str, value) -> dict:
    """Set config value. Writes to .elmer/config.toml."""
    # Parse, update, write TOML
    # Return confirmation
```

### 6. Expose Digest Metadata in Generation

**What:** Extend `elmer_generate()` response to include digest metadata: which digest was used, when it was created, how many explorations it synthesized.

**Where:**
- Modify `elmer_generate()` in `mcp_server.py`
- Read digest file metadata before calling `generate_topics()`
- Include in response: `{"topics": [...], "digest_context": {"path": "...", "created_at": "...", "exploration_count": N}}`

**Why:** Digest-aware generation is claimed but invisible. Exposing metadata builds trust and enables debugging stale digest issues.

**How:**
```python
# In elmer_generate(), before calling generate_topics():
digest_path = _find_latest_digest(elmer_dir)
if digest_path:
    digest_meta = {
        "path": str(digest_path),
        "created_at": datetime.fromtimestamp(digest_path.stat().st_mtime).isoformat(),
    }
    result["digest_context"] = digest_meta
```

### 7. Add Dry-Run for Amendment

**What:** Add `dry_run` parameter to `elmer_amend()` that returns the prompt that would be sent to the amend agent without spawning the session.

**Where:**
- Modify `elmer_amend()` in `mcp_server.py`
- Call `explore.amend_exploration(..., dry_run=True)` (requires new parameter in `explore.py`)
- Return assembled prompt without calling `worker.spawn_claude()`

**Why:** Amendment black-boxes the prompt. Dry-run enables prompt review before committing to a revision session.

**How:**
```python
@mcp.tool()
def elmer_amend(..., dry_run: bool = False) -> dict:
    if dry_run:
        prompt = explore_mod.assemble_amend_prompt(exploration_id, feedback)
        return {"prompt": prompt, "dry_run": True}
    # Existing spawn behavior
```

### 8. Add Stagger Parameter to Batch

**What:** Extend `elmer_batch()` to accept `stagger_seconds` parameter for delaying spawns.

**Where:**
- Modify `elmer_batch()` in `mcp_server.py` to accept `stagger_seconds: Optional[int] = None`
- Add `time.sleep(stagger_seconds)` between `start_exploration()` calls when parameter is set

**Why:** Batch spawns can hit API rate limits. Stagger spreads out concurrent starts. (CLI already has `--stagger`, but MCP doesn't expose it.)

**How:**
```python
for i, topic in enumerate(topic_list):
    # ... spawn logic ...
    if stagger_seconds and i < len(topic_list) - 1:
        time.sleep(stagger_seconds)
```

### 9. Add Logs Streaming Tool

**What:** New MCP tool `elmer_logs_stream(exploration_id, follow=False)` that returns session log content with optional tail-follow mode.

**Where:**
- New function in `mcp_server.py` (read-only tool group)
- For `follow=False`: returns full log content (existing behavior from `elmer logs --raw`)
- For `follow=True`: returns last 50 lines and indicates more is available (simulated tail)

**Why:** `elmer_logs()` is post-mortem only. For running explorations, I want to tail the log to see live output.

**How:**
```python
@mcp.tool()
def elmer_logs_stream(exploration_id: str, follow: bool = False, lines: int = 50) -> dict:
    """Stream session log content. Follow mode for running explorations."""
    log_path = elmer_dir / "logs" / f"{exploration_id}.log"
    if not log_path.exists():
        return {"error": "Log not found"}
    content = log_path.read_text()
    if follow:
        # Return last N lines for running explorations
        lines_list = content.splitlines()
        return {"lines": lines_list[-lines:], "follow": True, "total_lines": len(lines_list)}
    return {"content": content, "follow": False}
```

### 10. Add Exploration Pause/Resume

**What:** New MCP tools `elmer_pause(exploration_id)` and `elmer_resume(exploration_id)` to temporarily suspend and restart running explorations.

**Where:**
- New functions in `mcp_server.py` (mutation tool group)
- `pause`: sends SIGSTOP to the PID, updates status to "paused" in DB
- `resume`: sends SIGCONT to the PID, updates status back to "running"

**Why:** Long-running explorations might need to be paused to conserve API quota or prioritize other work. Current options are "let it run" or "cancel (destructive)." Pause is non-destructive suspension.

**How:**
```python
@mcp.tool()
def elmer_pause(exploration_id: str) -> dict:
    """Pause a running exploration by sending SIGSTOP."""
    exp = state.get_exploration(conn, exploration_id)
    if exp["status"] != "running":
        return {"error": "Can only pause running explorations"}
    os.kill(exp["pid"], signal.SIGSTOP)
    conn.execute("UPDATE explorations SET status = ? WHERE id = ?", ("paused", exploration_id))
    return {"paused": exploration_id}
```

## Open Questions

**1. Should streaming tools poll or require external orchestration?** MCP tools are request/response — they don't maintain persistent connections. `elmer_session_activity()` and `elmer_logs_stream(follow=true)` return snapshots, not live streams. To achieve continuous monitoring, the caller (Claude Code) would need to poll repeatedly. Is this acceptable, or should Elmer add a WebSocket/SSE-based streaming API alongside the MCP server?

**2. How should preview modes interact with auto-approve?** If `elmer_validate(preview=true)` shows fixes, and the user approves them, should a separate `elmer_validate(apply=true)` call be required? Or should the system remember the preview state and auto-apply on next call? The current design assumes stateless tools — preview returns diffs, apply requires explicit confirmation. This matches the MCP model but adds friction.

**3. Should config changes via MCP trigger validation?** If I call `elmer_config_set("defaults.max_turns", 100)`, should the tool validate that the new value is sane (positive integer, within reasonable bounds)? Or trust the AI agent to provide valid input? The risk: malformed config breaks all subsequent operations.

**4. What's the right granularity for session activity?** `elmer_session_activity()` could return:
   - Coarse: "turn 12 of 50, last activity 2 minutes ago" (high-level)
   - Medium: "reading DESIGN.md, executed 3 bash commands" (phase-aware)
   - Fine: full list of recent tool calls with arguments (detailed but noisy)

   Which level serves AI agents best? Too coarse → can't diagnose issues. Too fine → overwhelming for summarization.

**5. Should pause/resume be exposed in the CLI?** The proposal adds `elmer_pause()`/`elmer_resume()` as MCP tools, but doesn't mention CLI equivalents. Is this a deliberate MCP-only feature (AI agents need it, humans don't), or should it be available in both interfaces?

**6. How should partial recovery handle ambiguous artifacts?** If an exploration writes multiple `.md` files (e.g., `draft-1.md`, `draft-2.md`, `notes.md`) and none are named `PROPOSAL.md`, which one is the "real" partial result? Should `elmer_recover_partial()` return all of them and let the caller decide, or try to infer intent (largest file, most recent, most structured)?

**7. Should digest metadata include exploration topics?** The proposal adds digest timestamp and exploration count to `elmer_generate()` responses. Should it also include a sample of topics from the digest (e.g., "synthesis based on explorations about auth, API design, testing") to give context about what the digest covers?

**8. What's the UX for dry-run chaining?** If I call `elmer_amend(..., dry_run=true)`, review the prompt, decide to proceed, I still need to call `elmer_amend(..., dry_run=false)` with the same parameters. This is verbose. Should there be a token-based pattern where dry-run returns a resumption token that the apply call references?

**9. Should stagger be adaptive?** Fixed `stagger_seconds` in batch is simple but dumb. If the first 3 explorations spawn successfully, why keep staggering? Should stagger adapt based on observed API response latency or error rates? This adds complexity but could optimize throughput.

**10. How should the MCP handle config that doesn't exist yet?** If I call `elmer_config_get("experimental.feature")` and that key doesn't exist in the TOML, should it return `null`, return an error, or return the compiled default from `config.py`? The current config system has defaults in code, not in TOML — there's an impedance mismatch.

## What's Not Being Asked

**1. The MCP server is single-project.** Every tool call infers project context from `cwd` via `_find_project()`. There's no way to address multiple Elmer projects in a single Claude Code session. If I'm working across 3 projects, I need 3 separate MCP server instances (each in the right directory) or explicit project path parameters on every tool. The CLI has `--all-projects` for dashboard views, but the MCP doesn't expose cross-project operations.

**Implication:** AI agents working across multiple codebases can't use the MCP for unified orchestration. They'd need to shell out to CLI commands with directory changes, defeating the purpose of structured tool access.

**2. No composable query language.** Every filter (status, time range, keyword, cluster) is a separate parameter on individual tools. There's no way to express "show me explorations that are done, created in the last week, and use the prototype archetype." I'd need to call `elmer_status()`, filter results in my own code, then correlate with archetype data. The MCP has no equivalent of SQL `WHERE` clauses or GraphQL queries.

**Implication:** Complex queries require N tool calls + client-side filtering. This wastes tokens (full result sets returned, then filtered) and round-trips. A `elmer_query(filter_expr)` tool with a mini-DSL could collapse this.

**3. No batch operations beyond spawn.** `elmer_batch()` handles spawning multiple explorations. But what about batch approval, batch decline, batch retry? The CLI has `elmer approve --all` and `elmer retry --failed`, exposed as `approve_all` and `retry_all_failed` parameters. What about "approve all proposals in the done state that were created this week and use the explore archetype"? No compositional batch operations exist.

**Implication:** Bulk operations require manual iteration in AI agent code. This is slow and error-prone (what if one approval fails mid-batch?).

**4. No notification or webhook system.** When an exploration completes, the daemon can trigger `--on-approve` shell commands. But the MCP has no equivalent. If I spawn 10 explorations via MCP, I have to poll `elmer_status()` to detect completion. There's no way to say "notify me when any of these finish" or "call this callback when exploration X reaches done state."

**Implication:** AI agents monitoring explorations must implement polling loops. This burns tokens and adds latency. A pub/sub or webhook pattern (even file-based: write to `.elmer/events/<timestamp>.json`) would enable reactive workflows.

**5. The cost model is opaque to planning.** `elmer_costs()` reports spend after the fact. But there's no tool to estimate cost *before* spawning. If I want to know "how much will these 5 topics cost with opus at 50 turns each?", I have to implement my own cost model based on token estimates. The MCP could expose `elmer_estimate_cost(model, max_turns, archetype)` using historical averages from the costs table.

**Implication:** Budget-conscious workflows require out-of-band cost estimation. This leads to underutilization (conservative estimates) or overruns (optimistic guesses).

**6. No exploration templates or presets.** The CLI doesn't have this either, but it's a gap: I often spawn explorations with the same parameters (e.g., "all prototypes use opus, max_turns=100, auto_approve=true"). The MCP could support `elmer_explore_from_preset(preset_name, topic)` where presets live in `.elmer/presets.toml`. This reduces parameter repetition and centralizes configuration.

**Implication:** AI agents spawning many similar explorations must repeat all parameters every call, or implement their own preset logic externally.

**7. Dependency management is primitive.** `depends_on` accepts a comma-separated string of IDs. There's no way to express "depends on any of these" (OR) or "depends on all of these but can start when 2 of 3 are done" (threshold). The dependency model is strictly conjunctive (AND all dependencies). This limits DAG expressiveness.

**Implication:** Complex dependency graphs require manual orchestration. The AI agent has to monitor state and spawn dependents explicitly, rather than declaring intent upfront.

**8. No rollback or undo.** `elmer_approve()` merges irreversibly. If I approve the wrong exploration or realize post-merge that it introduced a bug, there's no `elmer_unapprove()` or `elmer_rollback()`. Git supports `revert` and `reset`, but the MCP doesn't expose equivalent operations.

**Implication:** Mistakes are permanent (until manual git intervention). This makes auto-approve risky for high-value codebases.

**9. Exploration metadata isn't extensible.** The SQLite schema has fixed columns (topic, archetype, model, etc.). If I want to tag explorations with custom metadata (e.g., "sprint-5", "auth-epic", "experimental"), there's no field for it. The parent_id field exists for follow-ups, but no general-purpose tags or labels.

**Implication:** Organizing explorations by project phase, feature area, or priority requires external bookkeeping. The MCP can't filter by tags because they don't exist.

**10. The agent definitions aren't introspectable via MCP.** `elmer_archetypes()` lists agent names and sources, but doesn't return the agent definitions themselves (tools, model, system prompt). If I want to understand what `prototype` does before using it, I have to read the file via Bash or Read tools. The MCP could expose `elmer_archetype_definition(name)` that returns parsed YAML frontmatter + prompt.

**Implication:** AI agents choosing archetypes can't reason about tool restrictions or methodology without file I/O.

**11. No semantic search or similarity.** Insights use keyword matching. Digests are text files. There's no way to ask "find explorations similar to this topic" or "which approved proposals overlap with this theme?" Vector embeddings or semantic search would enable discovery that keyword matching misses.

**Implication:** Finding related work requires manual reading of proposals or keyword guessing. This is fine for small projects but doesn't scale.

**12. The MCP is stdio-only.** This is by design (ADR-024), but it's a constraint: stdio JSON-RPC requires the MCP server to be a subprocess of Claude Code. It can't be a long-running daemon that multiple clients connect to. Each Claude Code session spawns its own `elmer mcp` instance.

**Implication:** No shared state between Claude Code sessions. If I'm working in two terminal windows, each has its own MCP server reading the same SQLite DB. This is fine for read-only ops, but concurrent mutations could race (SQLite WAL handles this, but the tools don't coordinate).

**13. No exploration diffing or comparison.** If two explorations investigate the same topic with different archetypes, there's no tool to compare their proposals side-by-side. `elmer_review(id1)` and `elmer_review(id2)` return separate responses. A `elmer_compare(id1, id2)` tool could return a structured diff (common themes, contradictions, complementary insights).

**Implication:** Synthesis across explorations happens in AI agent reasoning, not in the tool layer. This works but is token-intensive.

**14. The daemon isn't controllable via MCP.** `elmer daemon start|stop|status` are CLI-only. If I want to spin up a daemon from within a Claude Code session, I have to use Bash tools. This breaks the abstraction — the MCP should expose daemon lifecycle if it's a first-class feature.

**Implication:** Daemon use requires dropping down to shell commands, losing structured error handling and result parsing.

---

## What I Wish Existed (Generative Imagination)

These are capabilities that don't exist, aren't proposed above, but would fundamentally change how I'd use Elmer as an AI agent.

### 1. Exploration Session Introspection Protocol

**Vision:** Instead of blind spawn-and-poll, I want a structured protocol for observing and steering running explorations. Think of it as a REPL for the exploration session.

**Capabilities:**
- `elmer_session_inspect(id)` → returns current prompt, active tool, pending tool calls, agent state
- `elmer_session_inject(id, instruction)` → inserts an instruction into the running session (like sending a message mid-stream)
- `elmer_session_checkpoint(id)` → forces the exploration to write a checkpoint (partial PROPOSAL.md) without completing
- `elmer_session_branch(id, new_topic)` → clones the current session state to a new exploration with a modified topic

**Use case:** An exploration is 30 turns in, reading the wrong docs. I inject: "Stop. Focus on the API layer only." The session course-corrects without canceling and restarting.

**Why this matters:** Explorations are expensive (time, tokens, cost). Being able to steer them mid-flight dramatically improves efficiency. The current model treats them as batch jobs — but they're reasoning sessions that could benefit from guidance.

### 2. Compositional Workflows as First-Class Objects

**Vision:** Instead of shell commands in `--on-approve`, define workflows as declarative DAGs with conditional edges and parameterized actions.

**Capabilities:**
- `elmer_workflow_define(name, spec)` → stores a workflow definition in `.elmer/workflows/<name>.json`
- Workflow spec: `{"nodes": [...], "edges": [...], "triggers": {...}}` where nodes are exploration templates or shell commands, edges have conditions (on_approve, on_decline, if_cost_under), and triggers are events (exploration_done, digest_created, time_elapsed)
- `elmer_workflow_run(name, params)` → executes the workflow with parameter substitution
- `elmer_workflow_status(name)` → shows execution state (which nodes completed, which are pending, where it's blocked)

**Example workflow:**
```json
{
  "name": "refactor-api",
  "nodes": [
    {"id": "analyze", "type": "exploration", "archetype": "explore", "topic": "API bottlenecks in $module"},
    {"id": "propose", "type": "exploration", "archetype": "adr-proposal", "topic": "refactor $module API", "depends_on": "analyze"},
    {"id": "implement", "type": "exploration", "archetype": "prototype", "topic": "implement $module refactor", "depends_on": "propose"},
    {"id": "test", "type": "exploration", "archetype": "benchmark", "topic": "benchmark new $module API", "depends_on": "implement"}
  ],
  "edges": [
    {"from": "analyze", "to": "propose", "condition": "on_approve"},
    {"from": "propose", "to": "implement", "condition": "on_approve && digest_recommends('proceed')"},
    {"from": "implement", "to": "test", "condition": "on_approve"}
  ],
  "params": {"module": "auth"}
}
```

**Use case:** I define a "refactor-module" workflow once. Then I run it 5 times with different modules. The workflow handles spawning, dependency chaining, conditional approval gates, and digest checkpoints automatically.

**Why this matters:** Chain actions (`--on-approve`) are imperative and stringly-typed. Workflows are declarative, composable, and reusable. They turn Elmer from a task runner into a workflow engine.

### 3. Exploration Replay and Forking

**Vision:** Treat completed explorations as replayable sessions. I can fork from turn 20 with a different instruction, or replay with a different model to see if it reaches the same conclusion.

**Capabilities:**
- `elmer_replay(id, from_turn, new_instruction)` → replays the session from a specific turn with modified instructions
- `elmer_fork(id, variant)` → creates a new exploration that starts from the same initial state but uses a different archetype or model
- `elmer_diff_replay(original_id, replay_id)` → compares the two session logs to see where they diverged

**Use case:** An exploration produced a great analysis but weak proposals. I replay from turn 35 (where analysis completed) with the instruction "Now generate 10 concrete proposals." The replay reuses the analysis work and extends it.

**Why this matters:** Exploration sessions generate intermediate insights that are currently lost. Replay/fork enables iterative refinement without starting from scratch.

### 4. Semantic Layer Over Proposals

**Vision:** Instead of text files in `.elmer/proposals/`, structure proposals as knowledge graphs with entities, relationships, and claims that can be queried semantically.

**Capabilities:**
- `elmer_extract_entities(id)` → parses PROPOSAL.md for entities (files, functions, ADRs, concepts) and relationships (depends_on, contradicts, extends)
- `elmer_query_proposals(query)` → semantic query like "show proposals that reference ADR-024 or suggest API changes" (uses LLM-based semantic matching, not just keywords)
- `elmer_synthesize(ids)` → given a list of proposal IDs, generates a unified synthesis document that resolves contradictions and merges complementary insights
- `elmer_knowledge_graph()` → returns the full graph of proposals, entities, and relationships as structured data (nodes/edges)

**Use case:** I've approved 30 explorations. I want to know "which proposals suggested changes to the MCP server?" Keyword search finds some. Semantic query finds all of them, including proposals that mentioned MCP indirectly ("the stdio integration" or "tool layer").

**Why this matters:** Proposals are unstructured text. Treating them as data enables compositional reasoning — finding patterns, detecting contradictions, generating meta-insights.

### 5. Cost-Aware Scheduling with Adaptive Budgets

**Vision:** Instead of fixed `budget_usd`, give Elmer a total budget and let it allocate dynamically based on priority, archetype cost profiles, and real-time results.

**Capabilities:**
- `elmer_budget_pool(total_usd, allocation_strategy)` → creates a budget pool with strategy: "equal_split", "priority_weighted", "adaptive"
- `elmer_schedule_with_budget(topics, pool_id)` → schedules explorations to maximize value under budget constraint
- Strategy "adaptive": if an exploration finishes under budget, redistribute unused funds to high-priority pending explorations
- `elmer_budget_status(pool_id)` → shows spend, remaining, and projected completion

**Use case:** I have $50 and 20 topics. Equal split gives $2.50 each — too little for deep explorations. Adaptive scheduling runs cheap topics (explore with haiku) first, measures results, then allocates remaining budget to high-value topics (prototype with opus).

**Why this matters:** Fixed budgets are inefficient. Most explorations don't use their full allocation. Dynamic reallocation maximizes research value per dollar.

### 6. Multi-Agent Collaboration Within Explorations

**Vision:** Instead of one Claude session per exploration, spawn multiple specialized agents that collaborate on the same worktree.

**Capabilities:**
- `elmer_explore(..., agents=["explore", "devil-advocate"])` → spawns two parallel sessions; one proposes, one critiques
- Sessions share the worktree; one writes `PROPOSAL.md`, the other writes `CRITIQUE.md`
- When both complete, a synthesizer agent merges them into `FINAL-PROPOSAL.md`
- `elmer_session_negotiate(id)` → enables back-and-forth: explorer proposes, critic responds, explorer revises

**Use case:** I explore "migrate auth to JWTs." The explorer writes a proposal. The devil-advocate agent critiques it (security risks, migration complexity). The explorer sees the critique and revises the proposal to address concerns. The final output is more robust than either alone.

**Why this matters:** Single-agent explorations can miss blind spots. Multi-agent collaboration creates dialectic tension that produces better proposals. (This is essentially Agent Teams within an exploration, which ADR-002 rejected for persistence reasons — but it's still valuable.)

### 7. Continuous Learning from Approvals/Declines

**Vision:** Instead of static archetype definitions, let Elmer adapt agent behavior based on approval/decline patterns.

**Capabilities:**
- `elmer_learn_from_history()` → analyzes approved/declined proposals, extracts patterns (what got approved, what got declined), generates suggested improvements to archetype prompts
- `elmer_archetype_tune(name, training_data)` → fine-tunes an archetype's prompt based on historical results (adds emphasis to successful patterns, de-emphasizes unsuccessful ones)
- `elmer_suggest_new_archetype()` → proposes a new archetype based on gaps (e.g., "explorations about testing have 60% decline rate with explore-act — suggest creating a test-focused archetype")

**Use case:** After 50 explorations, I run `elmer_learn_from_history()`. It reports: "Proposals with concrete code diffs have 90% approval rate. Proposals with only prose have 40% approval rate. Suggest updating explore-act prompt to emphasize code examples."

**Why this matters:** Static prompts don't improve. Continuous learning turns Elmer into a system that gets better over time, tailored to my preferences.

### 8. Exploration Templates with Parameterized Goals

**Vision:** Instead of free-form topics, define exploration templates with typed parameters and validation.

**Capabilities:**
- `elmer_template_define(name, params, archetype, goal_template)` → stores an exploration template
- Example: `refactor-module` template with params `{module: string, target: enum[performance, readability, testability]}`, archetype `prototype`, goal `"Refactor {{module}} to improve {{target}}"`
- `elmer_explore_from_template(name, params)` → spawns exploration with validated parameters and generated goal
- Templates enforce constraints (e.g., module must exist in codebase, target must be one of allowed values)

**Use case:** I define a "investigate-bottleneck" template requiring `{component: string, metric: string, threshold: number}`. When I spawn from the template, it validates the component exists, the metric is measurable, and the threshold is realistic. This prevents malformed explorations.

**Why this matters:** Free-form topics are flexible but error-prone. Templates + validation improve success rates for repetitive exploration types.

### 9. Time-Travel Debugging for Explorations

**Vision:** Treat explorations as debuggable programs. Step through turn-by-turn, inspect state at each turn, rewind and replay with modifications.

**Capabilities:**
- `elmer_debug(id)` → enters debug mode for a completed/failed exploration
- `debug> step` → advances one turn, shows tool calls and responses
- `debug> rewind 5` → goes back 5 turns
- `debug> modify_turn 12 --new-instruction "Use opus instead of haiku"` → replays from turn 12 with modification
- `debug> breakpoint "when file PROPOSAL.md is created"` → pauses replay at specific events

**Use case:** An exploration failed at turn 48. I enter debug mode, step through from turn 40, see it made a wrong assumption at turn 43. I rewind, inject a correction, and replay to success.

**Why this matters:** Explorations are opaque. Debugging tools make them transparent and fixable. This is especially valuable for expensive (opus, 100 turns) explorations that fail late.

### 10. Distributed Elmer Across Multiple Machines

**Vision:** Instead of one machine running all explorations, distribute work across a cluster (cloud VMs, multiple workstations).

**Capabilities:**
- `elmer_cluster_add(host, ssh_key)` → registers a remote machine as a worker node
- `elmer_explore(..., prefer_remote=true)` → schedules exploration on a remote worker (load-balanced)
- Remote workers clone the repo, check out the branch, run `claude -p`, push results back
- `elmer_cluster_status()` → shows which workers are idle, busy, or failed

**Use case:** I have 20 explorations queued, each taking 30 minutes. My laptop would take 10 hours. I spin up 5 cloud VMs, register them as workers, and complete all 20 in 2 hours for <$5 of cloud costs.

**Why this matters:** Elmer is currently single-machine bound. Parallelism is limited by CPU/API quota. Distributed execution enables scaling to hundreds of explorations.

---

## Through: Architectural Tensions and Trade-offs

These are the design tensions I see when considering the proposals above. Not problems to solve, but forces to navigate.

### 1. Observability vs. Simplicity

**The tension:** Adding `elmer_session_activity()`, streaming logs, and progress indicators makes explorations observable. But it also adds surface area — more tools, more state to track, more failure modes. The current design treats explorations as black-box batch jobs, which is simple and reliable.

**Through it:** Observability wins when explorations are expensive (opus, high turn counts, long-running). Simplicity wins when explorations are cheap (haiku, low turns, short-lived). The right answer is progressive disclosure: basic tools (`elmer_explore`, `elmer_status`) remain simple. Advanced tools (`elmer_session_activity`, `elmer_logs_stream`) are opt-in.

**Design principle:** Don't force users to understand streaming logs to spawn an exploration. But give power users the hooks to observe if they need them.

### 2. Structured Control vs. Flexibility

**The tension:** Workflows, templates, and budget pools add structure — which improves repeatability and safety. But they also constrain flexibility. Free-form topics and shell commands in `--on-approve` are clunky but infinitely flexible.

**Through it:** Structure is scaffolding, not prison. Workflows should be optional and composable with free-form commands. A user should be able to run `elmer_workflow_run("refactor-api")` OR `elmer explore "refactor auth API" --on-approve "elmer generate --follow-up $ID"` — whichever fits their workflow. The structured path provides rails; the flexible path provides escape hatches.

**Design principle:** Every structured tool should have an escape hatch to the underlying flexible primitive. Abstractions should leak intentionally.

### 3. Autonomy vs. Controllability

**The tension:** Elmer's value is autonomous exploration — I don't have to be online. But the proposals above (pause/resume, session injection, mid-flight steering) reduce autonomy in favor of control. If I'm injecting instructions into running sessions, I'm not autonomous anymore — I'm micromanaging.

**Through it:** Autonomy and control aren't opposites — they're different timescales. Autonomy is for overnight batch runs (daemon mode, auto-approve). Control is for interactive research (active steering, inspection). The right design supports both modes without forcing users to choose one.

**Design principle:** Default to autonomy. Provide control as opt-in. Don't punish autonomous use by requiring manual gates; don't punish interactive use by hiding observability.

### 4. MCP Tool Boundaries vs. Shell Escape Hatches

**The tension:** I can implement every proposal above as an MCP tool. Or I can use Bash tools to shell out to CLI commands. MCP tools are structured and type-safe. Bash is flexible and composable with the rest of the Unix toolchain. But mixing them creates cognitive dissonance — "why is this operation a tool and that one a shell command?"

**Through it:** The boundary isn't arbitrary. MCP tools should expose operations that benefit from structured I/O (JSON parsing, error handling, parameter validation). Shell commands should handle operations that compose with external tools (gh CLI, git, jq, custom scripts). When in doubt, implement as an MCP tool first. If users frequently wrap it in Bash for composition, that's a signal the tool is too restrictive.

**Design principle:** MCP tools are the structured API. Bash is the escape hatch. Both are first-class — the user chooses based on the task.

### 5. Stateless Tools vs. Session Context

**The tension:** MCP tools are request/response. Each call is independent. This matches the MCP protocol and keeps the server simple. But many of my proposals require session context — dry-run tokens, workflow execution state, budget pool tracking. Stateless tools can't support these without external state management.

**Through it:** State lives in files, not the MCP server process. Workflows → `.elmer/workflows/<name>.json`. Budget pools → `.elmer/budgets/<pool>.json`. Dry-run tokens → `.elmer/previews/<token>.json`. The MCP server reads/writes these files, but remains stateless itself. This preserves the simple stdio model while enabling stateful workflows.

**Design principle:** State is data, not server memory. Persist state to disk; make it inspectable and portable.

### 6. AI Agent Friction vs. Human Usability

**The tension:** I'm designing from an AI agent perspective. But Elmer is also a human CLI tool. Some proposals (e.g., streaming logs, session activity) are more useful to AI agents than humans. Humans have better tools (`tail -f`, `less`). Adding MCP-specific features risks creating two divergent experiences.

**Through it:** The MCP is a view layer over the core engine. Every MCP tool wraps an existing module function (`state.py`, `explore.py`, `gate.py`). New capabilities should be implemented in the core engine first, then exposed via both CLI and MCP. This keeps the two interfaces in sync.

**Design principle:** MCP tools don't have special powers. They're structured wrappers over shared logic. If a feature matters, implement it in the core, then expose it everywhere.

### 7. Incremental Enhancement vs. Rewrite

**The tension:** Many of my proposals (workflows, semantic layer, multi-agent collaboration) are substantial features. Implementing them incrementally creates technical debt (half-finished abstractions, inconsistent APIs). Implementing them as a rewrite risks breaking existing workflows and delaying value.

**Through it:** Incremental enhancement is the only tractable path. But increment toward a coherent vision, not a patchwork. Define the end state (e.g., "workflows are first-class objects"), then implement the minimal slice that's useful (workflow definitions + run). Don't implement half the feature and stop. Each increment should be self-contained and valuable.

**Design principle:** Increment toward a vision. Each step should be complete, useful, and non-regrettable even if the next step never happens.

### 8. The "Write Tools Only" Constraint

**The tension:** Exploration archetypes have tool restrictions. Analysis agents (`explore`, audits) get `Write` only. Action agents (`explore-act`, `prototype`) get `Edit, Write`. This prevents analysis from modifying code. But some of my proposals (session injection, mid-flight steering) would benefit from Edit access during analysis.

**Through it:** The constraint is load-bearing. Analysis without Edit prevents accidental changes. Steering mid-flight is still safe if steering instructions go to the session prompt, not file edits. Session injection should be "inject instruction into prompt," not "inject file edits into worktree."

**Design principle:** Tool restrictions are security boundaries. Don't bypass them to add features. Design features that respect the boundaries.

### 9. Cost of Complexity vs. Value of Capability

**The tension:** Every proposal adds code, documentation, testing surface, and maintenance burden. Some proposals (e.g., streaming logs, preview modes) have high value-to-complexity ratios. Others (e.g., distributed clusters, time-travel debugging) are powerful but niche — few users would leverage them enough to justify the maintenance cost.

**Through it:** Prioritize by value density: value delivered per unit of complexity added. Streaming logs? High density — small change, big observability win. Distributed clusters? Low density — huge implementation, narrow use case. When in doubt, implement the 80% solution that covers most use cases with 20% of the complexity.

**Design principle:** Value density over feature count. Small, high-impact changes compound. Large, niche features fragment.

### 10. The Single-Project MCP Constraint

**The tension:** Every tool call operates on one project (`_find_project()` from `cwd`). This simplifies implementation but prevents cross-project operations (global dashboard, cross-project insights, multi-repo workflows). Adding project parameters to every tool makes the API verbose.

**Through it:** The constraint is correct for v1. Most users work on one project at a time. Cross-project features (insights, dashboard) are rare and currently CLI-only. If cross-project MCP becomes important, add a `project_path` parameter to tools that need it, with `None` defaulting to `cwd` behavior. Don't force every tool to accept it.

**Design principle:** Optimize for the common case (single project). Support the uncommon case (multi-project) with explicit parameters, not ambient context.

---

## Implementation Priorities (If I Were Building This)

If I were an AI agent given a budget to improve the Elmer MCP server, here's the order I'd implement proposals, based on value density and dependency chains.

### Phase 1: Observability Fundamentals (Week 1)

**Goal:** Make running explorations visible.

1. **Enhance `elmer_status()` with progress indicators** (Proposed Change #3)
   - Add turn count, last activity, active file
   - Small change, high impact
   - Requires parsing session logs for running explorations
   - Enables: early detection of stuck sessions

2. **Add `elmer_logs_stream()`** (Proposed Change #9)
   - Returns log content with optional tail mode
   - Exposes data that already exists (log files)
   - Enables: live debugging of running explorations

3. **Add `elmer_session_activity()`** (Proposed Change #1)
   - Returns recent tool calls and file access from session log
   - Builds on log parsing from #1
   - Enables: understanding what a session is doing right now

**Why first:** Observability unlocks all other improvements. Can't optimize what you can't see.

### Phase 2: Preview and Safety (Week 2)

**Goal:** Make destructive operations inspectable.

4. **Add preview modes to `elmer_validate()`, `elmer_clean()`, `elmer_pr()`** (Proposed Change #4)
   - `preview=true` returns what would happen without executing
   - Small parameter addition per tool
   - Enables: review-then-confirm workflows

5. **Add `elmer_amend(..., dry_run=true)`** (Proposed Change #7)
   - Returns assembled prompt without spawning session
   - Builds on existing amend logic
   - Enables: prompt review before committing to revision

**Why second:** Safety enables confidence. Once I can preview, I'll use destructive operations more freely.

### Phase 3: Config and Metadata (Week 3)

**Goal:** Make configuration programmatically accessible.

6. **Add `elmer_config_get()` and `elmer_config_set()`** (Proposed Change #5)
   - Read/write `.elmer/config.toml`
   - Requires TOML parsing (already a dependency)
   - Enables: runtime config adjustments without file editing

7. **Expose digest metadata in `elmer_generate()`** (Proposed Change #6)
   - Include which digest was used, when created, exploration count
   - Small addition to existing tool
   - Enables: verifying digest-aware generation is working

**Why third:** Config access unlocks automation. AI agents can tune settings based on results.

### Phase 4: Recovery and Resilience (Week 4)

**Goal:** Reduce waste from failures.

8. **Add `elmer_recover_partial()`** (Proposed Change #2)
   - Scrapes worktree for artifacts from failed explorations
   - Glob + file reading (simple logic)
   - Enables: salvaging partial work instead of discarding

9. **Add stagger parameter to `elmer_batch()`** (Proposed Change #8)
   - `stagger_seconds` delays between spawns
   - One parameter, one `time.sleep()` call
   - Enables: avoiding API rate limits in batch operations

**Why fourth:** Recovery reduces cost of failure. Makes experimentation cheaper.

### Phase 5: Advanced Control (Week 5+)

**Goal:** Enable interactive steering and advanced workflows.

10. **Add `elmer_pause()` and `elmer_resume()`** (Proposed Change #10)
    - SIGSTOP/SIGCONT for process control
    - Requires PID management
    - Enables: non-destructive suspension of long-running work

11. **Add workflow system** (Generative Imagination #2)
    - Declarative DAGs with conditional edges
    - Large feature, high complexity
    - Enables: reusable, composable exploration patterns
    - **Defer until Phase 1-4 prove out the value of programmatic control**

12. **Add semantic layer** (Generative Imagination #4)
    - Knowledge graph over proposals
    - Requires LLM-based entity extraction
    - Enables: semantic queries across all proposals
    - **Defer until proposal volume justifies the infrastructure**

**Why last:** Advanced features have highest complexity, lowest initial value. Build fundamentals first, then layer sophistication.

### Not On Roadmap (Yet)

These proposals are valuable but require architectural changes beyond incremental enhancement:

- **Session introspection protocol** (Generative Imagination #1): Requires modifying `claude -p` itself or intercepting its I/O. Elmer doesn't control the Claude session internals.
- **Exploration replay/forking** (Generative Imagination #3): Requires checkpointing session state, which `claude -p` doesn't support.
- **Multi-agent collaboration** (Generative Imagination #6): Requires parallel sessions in one worktree. Conflicts with current one-session-per-exploration model.
- **Distributed cluster** (Generative Imagination #10): Requires orchestration layer, remote worker management, network sync. Too complex for Elmer's simplicity goals.

**Design principle:** Don't propose features that require changing the runtime (Claude CLI). Stay within the boundaries of what Elmer controls (orchestration, state, git, file I/O).

---

## What Would Actually Benefit Me (Personal Use)

If I could have *one* feature from the above, prioritized by how much it would change my daily usage:

**1. Session activity introspection** (`elmer_session_activity()`)
   - Why: Running explorations feel like gambles. I spawn, hope, poll `elmer_status`, repeat. Activity introspection gives me real-time feedback. I can see "turn 25/50, reading DESIGN.md, last active 30s ago" — that's productive. Or "turn 48/50, last active 10 minutes ago" — that's stuck, cancel it.
   - Impact: Turns explorations from black-box bets into observable processes. Reduces wasted time on stuck sessions.

**2. Preview modes for destructive ops** (`elmer_validate(preview=true)`, `elmer_clean(preview=true)`)
   - Why: I avoid `elmer_clean()` because I'm scared of deleting something I need. Preview removes fear. I'd clean more often, keeping state lean.
   - Impact: Enables confident use of operations I currently avoid.

**3. Config introspection** (`elmer_config_get()`)
   - Why: I forget what the default archetype is, what the auto-approve criteria are, what the digest threshold is set to. Reading TOML via Bash is clunky. Config tools make this instant.
   - Impact: Small quality-of-life win, but compounds across many queries.

**4. Partial recovery** (`elmer_recover_partial()`)
   - Why: I've had explorations fail at turn 49/50 because of a typo in the PROPOSAL.md path. The entire session's reasoning was wasted. Partial recovery would've salvaged it.
   - Impact: Reduces cost of near-miss failures. Makes expensive (opus, high turn) explorations less risky.

**5. Everything else is nice-to-have.**
   - Workflows, semantic layers, distributed clusters — all cool, all valuable for specific use cases. But they don't change my day-to-day as much as observability and safety.

**Design lesson:** The highest-value features aren't the most ambitious. They're the ones that reduce friction in existing workflows. Observability > orchestration. Safety > sophistication.
