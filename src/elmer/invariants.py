"""Document invariant enforcement — validate documentation consistency post-merge."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config, state, worker


# Default invariant rules (used when no project-specific rules configured)
DEFAULT_RULES = [
    "ADR count in CLAUDE.md Orientation and DECISIONS.md header matches actual ## ADR- entries in DECISIONS.md",
    "Phase completion status in ROADMAP.md is consistent with CLAUDE.md Orientation",
    "No feature listed in ROADMAP.md without corresponding code in src/",
    "Tech stack canonical home is CLAUDE.md — other documents reference, not duplicate",
]


@dataclass
class InvariantResult:
    """Result of an invariant check."""

    invariant: str
    passed: bool
    detail: str


@dataclass
class ValidationResult:
    """Full validation result."""

    checks: list[InvariantResult]
    fixes: list[str]
    all_passed: bool
    cost_usd: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


def validate_invariants(
    *,
    elmer_dir: Path,
    project_dir: Path,
    model: str = "sonnet",
    max_turns: int = 5,
    rules: Optional[list[str]] = None,
    preview: bool = False,
) -> ValidationResult:
    """Run document invariant validation via AI.

    Returns ValidationResult with check outcomes and any fixes applied.

    If preview is True, runs in check-only mode: reports violations but
    does not apply fixes. The agent's Write and Edit tools are removed
    to enforce this.
    """
    if not worker.check_claude_available():
        raise RuntimeError(
            "claude CLI not found in PATH. Install Claude Code first."
        )

    # Load rules from config or use defaults
    if rules is None:
        cfg = config.load_config(elmer_dir)
        inv_cfg = cfg.get("invariants", {})
        rules = inv_cfg.get("rules", DEFAULT_RULES)

    rules_text = "\n".join(f"- {r}" for r in rules)

    agent_config = config.resolve_meta_agent(project_dir, "validate-invariants")

    preview_suffix = ""
    if preview:
        preview_suffix = (
            "\n\nIMPORTANT: This is a preview/check-only run. "
            "Report all violations but do NOT apply fixes. "
            "Do NOT use Write or Edit tools. Only read and report."
        )

    prompt = f"Check these invariant rules:\n\n{rules_text}{preview_suffix}"

    # Strip write tools in preview mode for enforcement
    if preview and agent_config is not None and "tools" in agent_config:
        agent_config = dict(agent_config)
        agent_config["tools"] = [
            t for t in agent_config["tools"]
            if t not in ("Write", "Edit", "NotebookEdit")
        ]

    # Run validation
    result = worker.run_claude(
        prompt=prompt,
        cwd=project_dir,
        model=model,
        max_turns=max_turns,
        agent_config=agent_config,
    )

    # Record cost
    conn = state.get_db(elmer_dir)
    state.record_meta_cost(
        conn,
        operation="validate_invariants",
        model=model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
    )
    conn.close()

    # Parse output
    checks = _parse_checks(result.output)
    fixes = _parse_fixes(result.output)
    all_passed = all(c.passed for c in checks) if checks else "ALL INVARIANTS PASS" in result.output

    return ValidationResult(
        checks=checks,
        fixes=fixes,
        all_passed=all_passed,
        cost_usd=result.cost_usd,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


def _parse_checks(output: str) -> list[InvariantResult]:
    """Parse INVARIANT/STATUS/DETAIL blocks from output."""
    checks = []
    current_invariant = None
    current_status = None

    for line in output.splitlines():
        line = line.strip()

        inv_match = re.match(r"^INVARIANT:\s*(.+)$", line, re.IGNORECASE)
        if inv_match:
            current_invariant = inv_match.group(1).strip()
            current_status = None
            continue

        status_match = re.match(r"^STATUS:\s*(PASS|FAIL)\s*$", line, re.IGNORECASE)
        if status_match and current_invariant:
            current_status = status_match.group(1).upper() == "PASS"
            continue

        detail_match = re.match(r"^DETAIL:\s*(.+)$", line, re.IGNORECASE)
        if detail_match and current_invariant is not None and current_status is not None:
            checks.append(InvariantResult(
                invariant=current_invariant,
                passed=current_status,
                detail=detail_match.group(1).strip(),
            ))
            current_invariant = None
            current_status = None

    return checks


def _parse_fixes(output: str) -> list[str]:
    """Parse FIXED: lines from output."""
    fixes = []
    for line in output.splitlines():
        match = re.match(r"^FIXED:\s*(.+)$", line, re.IGNORECASE)
        if match:
            fixes.append(match.group(1).strip())
    return fixes


# ---------------------------------------------------------------------------
# Document-only project detection (ADR-056)
# ---------------------------------------------------------------------------

# Build-system indicators: if any of these exist in project root, the project
# has code and should use code-level verification (build/test/lint).
_BUILD_INDICATORS = [
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Makefile",
    "CMakeLists.txt",
    "Cargo.toml",
    "go.mod",
    "build.gradle",
    "build.gradle.kts",
    "pom.xml",
    "Gemfile",
    "composer.json",
    "mix.exs",
    "Dockerfile",
]


def is_doc_only_project(project_dir: Path) -> bool:
    """Detect whether a project is documentation-only (no code build system).

    Returns True when the project has no recognized build-system files.
    Used to auto-select document-coherence verification as the completion
    check for plans in pre-code or doc-only projects (ADR-056).
    """
    for indicator in _BUILD_INDICATORS:
        if (project_dir / indicator).exists():
            return False
    return True


def run_coherence_check(
    *,
    elmer_dir: Path,
    project_dir: Path,
    model: str | None = None,
    max_turns: int | None = None,
) -> tuple[bool, str]:
    """Run document-coherence verification programmatically.

    Convenience wrapper around validate_invariants() for use as a plan
    completion check. Runs in check-only mode (no fixes applied).

    Returns (passed, detail_text) where detail_text is a human-readable
    summary suitable for logging.
    """
    cfg = config.load_config(elmer_dir)
    inv_cfg = cfg.get("invariants", {})
    model = model or inv_cfg.get("model", "sonnet")
    max_turns = max_turns or inv_cfg.get("max_turns", 5)

    result = validate_invariants(
        elmer_dir=elmer_dir,
        project_dir=project_dir,
        model=model,
        max_turns=max_turns,
        preview=True,
    )

    # Build a summary string
    lines = []
    for chk in result.checks:
        icon = "PASS" if chk.passed else "FAIL"
        lines.append(f"  {icon}: {chk.invariant}")
        if not chk.passed:
            lines.append(f"        {chk.detail}")

    passed_count = sum(1 for c in result.checks if c.passed)
    total = len(result.checks)
    lines.append(f"  {passed_count}/{total} invariants passed")

    detail = "\n".join(lines)
    return result.all_passed, detail
