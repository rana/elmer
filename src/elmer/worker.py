"""Claude CLI invocation for exploration sessions."""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ClaudeResult:
    """Result from a claude -p invocation."""

    output: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    num_turns: Optional[int] = None
    is_error: bool = False


def _parse_json_result(raw: str) -> ClaudeResult:
    """Parse JSON output from claude -p --output-format json.

    Expected format: a JSON object with fields like 'result', 'cost_usd',
    'num_turns', 'is_error', etc. Falls back to treating raw as plain text
    if JSON parsing fails.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Not JSON — treat as plain text output
        return ClaudeResult(output=raw.strip())

    # Handle both single-object and streaming (last object wins) formats
    if isinstance(data, list):
        # Streaming: take the last result-type object
        for obj in reversed(data):
            if isinstance(obj, dict) and obj.get("type") == "result":
                data = obj
                break
        else:
            # No result object found; use last item or fall back
            data = data[-1] if data else {}

    if not isinstance(data, dict):
        return ClaudeResult(output=raw.strip())

    return ClaudeResult(
        output=str(data.get("result", raw)).strip(),
        input_tokens=data.get("input_tokens"),
        output_tokens=data.get("output_tokens"),
        cost_usd=data.get("cost_usd") or data.get("total_cost_usd"),
        num_turns=data.get("num_turns"),
        is_error=bool(data.get("is_error", False)),
    )


def check_claude_available() -> bool:
    """Check if the claude CLI is available."""
    return shutil.which("claude") is not None


def _build_agent_flags(
    agent_config: Optional[dict], *, model_override: Optional[str] = None,
) -> list[str]:
    """Build --agents/--agent CLI flags from an agent config dict.

    agent_config should have: name, description, prompt, and optionally
    tools (list), model (str).

    If model_override is provided, the agent's own model field is omitted
    so that the caller's --model flag takes precedence.

    Returns a list of CLI arguments to prepend to the command.
    """
    if not agent_config:
        return []

    name = agent_config["name"]

    # Build the inline agent definition for --agents JSON
    agent_def: dict = {
        "description": agent_config.get("description", "Elmer agent"),
        "prompt": agent_config["prompt"],
    }
    if "tools" in agent_config:
        agent_def["tools"] = agent_config["tools"]
    # Only embed agent model when caller doesn't override it
    if not model_override and "model" in agent_config:
        agent_def["model"] = agent_config["model"]

    agents_json = json.dumps({name: agent_def})
    return ["--agents", agents_json, "--agent", name]


def spawn_claude(
    prompt: str,
    cwd: Path,
    model: str,
    log_path: Path,
    max_turns: int = 50,
    budget_usd: Optional[float] = None,
    agent_config: Optional[dict] = None,
) -> int:
    """Spawn a claude -p session in the background. Returns PID.

    If agent_config is provided, uses --agents/--agent flags to run with
    a custom Claude Code subagent definition. The agent's system prompt
    provides the methodology; the prompt arg provides the topic.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fd = open(log_path, "w")

    cmd = ["claude"]
    cmd.extend(_build_agent_flags(agent_config, model_override=model))
    cmd.extend([
        "-p", prompt,
        "--output-format", "json",
        "--model", model,
    ])
    cmd.extend(["--max-turns", str(max_turns)])
    if budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(budget_usd)])

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    log_fd.close()
    return proc.pid


def run_claude(
    prompt: str,
    cwd: Path,
    model: str,
    max_turns: int = 5,
    budget_usd: Optional[float] = None,
    agent_config: Optional[dict] = None,
) -> ClaudeResult:
    """Run a claude -p session synchronously. Returns ClaudeResult.

    If agent_config is provided, uses --agents/--agent flags to run with
    a custom Claude Code subagent definition.
    """
    cmd = ["claude"]
    cmd.extend(_build_agent_flags(agent_config, model_override=model))
    cmd.extend([
        "-p", prompt,
        "--output-format", "json",
        "--model", model,
    ])
    cmd.extend(["--max-turns", str(max_turns)])
    if budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(budget_usd)])

    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"claude exited with code {result.returncode}: {stderr}")

    raw = result.stdout.strip()
    if not raw:
        raise RuntimeError("claude produced no output")

    return _parse_json_result(raw)


def parse_log_costs(log_path: Path) -> Optional[ClaudeResult]:
    """Parse a completed session's JSON log file for cost data.

    Returns ClaudeResult with cost fields populated, or None on failure.
    Best-effort: cost tracking never blocks exploration flow.
    """
    try:
        raw = log_path.read_text().strip()
        if not raw:
            return None
        result = _parse_json_result(raw)
        # Only return if we got some cost data
        if result.cost_usd is not None or result.input_tokens is not None:
            return result
        return None
    except (OSError, ValueError):
        return None


def is_running(pid: int) -> bool:
    """Check if a process is still running."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but we can't signal it


def terminate(pid: int) -> bool:
    """Terminate a running process. Returns True if the process was stopped.

    Sends SIGTERM first for graceful shutdown, then SIGKILL after 5 seconds.
    """
    import signal
    import time

    if pid is None or not is_running(pid):
        return False

    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False

    # Wait up to 5 seconds for graceful exit
    for _ in range(50):
        if not is_running(pid):
            return True
        time.sleep(0.1)

    # Force kill
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass

    return not is_running(pid)
