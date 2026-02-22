"""Claude CLI invocation for exploration sessions."""

import os
import shutil
import subprocess
from pathlib import Path


def check_claude_available() -> bool:
    """Check if the claude CLI is available."""
    return shutil.which("claude") is not None


def spawn_claude(
    prompt: str,
    cwd: Path,
    model: str,
    log_path: Path,
    max_turns: int = 50,
) -> int:
    """Spawn a claude -p session in the background. Returns PID."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fd = open(log_path, "w")

    cmd = [
        "claude",
        "-p", prompt,
        "--model", model,
        "--max-turns", str(max_turns),
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    log_fd.close()
    return proc.pid


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
