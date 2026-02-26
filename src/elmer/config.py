"""Configuration loading and project initialization."""

import json
import shutil
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

GLOBAL_DIR = Path.home() / ".elmer"
PROJECTS_REGISTRY = GLOBAL_DIR / "projects.json"

ARCHETYPES_DIR = Path(__file__).parent / "archetypes"
AGENTS_DIR = Path(__file__).parent / "agents"

# Prefix for agent names in .claude/agents/ to avoid collisions
AGENT_PREFIX = "elmer-"
META_AGENT_PREFIX = "elmer-meta-"

DEFAULT_CONFIG = """\
[defaults]
archetype = "explore-act"
model = "opus"
max_turns = 50
generate_prompt = false

[generate]
count = 5
model = "sonnet"
max_turns = 5

[auto_approve]
model = "sonnet"
max_turns = 3
criteria = "document-only proposals with no code changes"
max_files_changed = 10
require_proposal = true
# policy: "review" (default, AI reviews every proposal) or
#         "verification_sufficient" (skip AI review when verify_cmd passes —
#         trust tests as the definitive quality gate, ADR-076)
policy = "review"

[archetype_selection]
model = "sonnet"
max_turns = 3

[followup]
enabled = false
count = 3
model = "sonnet"
auto_approve = false

[daemon]
interval = 600                  # seconds between cycles
auto_approve = false
auto_generate = false
auto_archetype = false            # AI selects archetype for generated topics
max_concurrent = 5
generate_threshold = 2          # generate new topics when active < threshold
generate_count = 5
max_approvals_per_cycle = 10    # safety bound: max auto-approvals per cycle

[insights]
enabled = false                 # extract insights after approval
model = "sonnet"
max_turns = 3
inject = true                   # inject cross-project insights into prompts
inject_limit = 5                # max insights to inject per exploration

[ensemble]
synthesis_model = "sonnet"
synthesis_max_turns = 15
# default_replicas = 3          # default replica count for --replicas
# default_archetypes = ["explore", "devil-advocate", "dead-end-analysis"]

[digest]
model = "sonnet"
max_turns = 5
threshold = 5                   # approvals since last digest before synthesizing
inject_into_explorations = true # inject latest digest into exploration prompts (G1)
# daemon auto-triggers digest when approvals >= threshold

[questions]
model = "sonnet"
max_turns = 5

[invariants]
model = "sonnet"
max_turns = 5
# rules = [                          # custom invariant rules (optional)
#   "ADR count in CLAUDE.md matches DECISIONS.md entries",
#   "Phase status in ROADMAP.md matches CLAUDE.md",
# ]

[audit]
enabled = false                       # enable audit scheduling in daemon
auto_approve = true                   # auto-review audit explorations
model = "sonnet"
max_turns = 50
# schedule: "archetype:topic" pairs, one per daemon cycle, rotating
# schedule = [
#   "consistency-audit:data model",
#   "consistency-audit:CLI interface",
#   "coherence-audit:",
#   "architecture-audit:state management",
#   "documentation-audit:",
#   "opportunity-scan:",
# ]

[session]
# max_hours = 4                  # watchdog: kill running sessions after N hours
# log_stale_minutes = 60         # watchdog: kill if log unchanged for N minutes
pending_ttl_days = 7              # auto-cancel pending explorations after N days

[hooks]
# Skill hooks: invoke project-defined Claude Code skills at lifecycle points.
# Skills must exist in .claude/skills/<name>/SKILL.md.
# Each hook receives the proposal text as context.
# on_done = ["mission-align"]           # run after PROPOSAL.md is committed
# pre_approve = ["cultural-lens"]       # run before auto-approve gate (must pass)
# post_approve = []                     # run after merge (informational only)
model = "sonnet"                        # model for skill hook sessions
max_turns = 10                          # per-hook turn limit

[verification]
# on_done = "pnpm build && pnpm test"  # global verification for all explorations
max_retries = 2                         # auto-amend attempts before marking failed

[implement]
model = "opus"                    # model for implementation sessions
decompose_model = "opus"          # model for milestone decomposition
decompose_max_turns = 30          # max turns for decomposition
max_turns = 50                    # per-step turn limit
# max_plan_hours = 8              # warn if estimated plan duration exceeds N hours

[implement.model_routing]
# Per-step model routing (B3): assign models based on step archetype or index.
# The decompose agent can set model per step; these are fallback defaults.
# scaffold = "opus"              # step 0 (scaffold/foundation)
# implement = "opus"             # implementation steps
# explore = "sonnet"             # analysis-only steps
# prototype = "sonnet"           # prototype steps
# fallback = "opus"              # any step without a specific route

# Per-million-token rates (USD) for cost estimation.
# Used only when claude CLI does not report actual cost.
[costs.rates]
haiku_input = 0.25
haiku_output = 1.25
sonnet_input = 3.00
sonnet_output = 15.00
opus_input = 15.00
opus_output = 75.00
"""

GITIGNORE = """\
worktrees/
logs/
digests/
plans/
state.db
daemon.pid
"""


def ensure_gitignore(elmer_dir: Path) -> None:
    """Ensure .elmer/.gitignore exists with current entries. Idempotent."""
    gitignore_path = elmer_dir / ".gitignore"
    gitignore_path.write_text(GITIGNORE)


def _ensure_vscode_watcher_exclusion(project_dir: Path) -> None:
    """Ensure .elmer/worktrees/ and logs/ are excluded from VSCode file watcher.

    Prevents IDE crashes from inotify event storms when worktrees are
    created/deleted rapidly during approve, decline, and clean operations.
    Only writes if the exclusion is missing — safe to run repeatedly.
    """
    vscode_dir = project_dir / ".vscode"
    settings_path = vscode_dir / "settings.json"

    exclusions = {
        ".elmer/worktrees/**": True,
        ".elmer/logs/**": True,
    }

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            return  # Don't corrupt existing settings
    else:
        settings = {}

    watcher = settings.get("files.watcherExclude", {})
    changed = False
    for pattern, value in exclusions.items():
        if pattern not in watcher:
            watcher[pattern] = value
            changed = True

    if changed:
        settings["files.watcherExclude"] = watcher
        vscode_dir.mkdir(exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=4) + "\n")


def init_project(project_dir: Path) -> Path:
    """Initialize .elmer/ in a project directory."""
    elmer_dir = project_dir / ".elmer"
    elmer_dir.mkdir(exist_ok=True)

    # Config
    config_path = elmer_dir / "config.toml"
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG)

    # Working directories
    (elmer_dir / "worktrees").mkdir(exist_ok=True)
    (elmer_dir / "logs").mkdir(exist_ok=True)

    # Gitignore for transient state (always overwrite to ensure current entries)
    ensure_gitignore(elmer_dir)

    # Exclude ephemeral dirs from IDE file watchers (prevents inotify storms)
    _ensure_vscode_watcher_exclusion(project_dir)

    # Register in global project registry
    register_project(project_dir)

    return elmer_dir


def load_config(elmer_dir: Path) -> dict:
    """Load .elmer/config.toml, returning defaults if missing."""
    config_path = elmer_dir / "config.toml"
    if config_path.exists():
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    return {"defaults": {"archetype": "explore-act", "model": "opus", "max_turns": 50}}


def validate_config(cfg: dict) -> list[str]:
    """Check config for common misconfiguration and interdependency issues.

    Returns a list of warning strings. Empty list means no issues found.
    This is a fast, deterministic check — no filesystem or AI access (ADR-076).
    """
    warnings: list[str] = []

    # 1. daemon.auto_approve requires [auto_approve] section
    daemon_cfg = cfg.get("daemon", {})
    if daemon_cfg.get("auto_approve") and "auto_approve" not in cfg:
        warnings.append(
            "[daemon] auto_approve = true but [auto_approve] section is missing — "
            "AI review gate will use hardcoded defaults"
        )

    # 2. daemon.auto_generate requires [generate] section
    if daemon_cfg.get("auto_generate") and "generate" not in cfg:
        warnings.append(
            "[daemon] auto_generate = true but [generate] section is missing — "
            "topic generation will use hardcoded defaults"
        )

    # 3. daemon.max_concurrent must be > 0
    max_concurrent = daemon_cfg.get("max_concurrent", 5)
    if isinstance(max_concurrent, (int, float)) and max_concurrent < 1:
        warnings.append(
            f"[daemon] max_concurrent = {max_concurrent} — must be >= 1"
        )

    # 4. generate_threshold should be < max_concurrent
    threshold = daemon_cfg.get("generate_threshold", 2)
    if (isinstance(threshold, (int, float)) and isinstance(max_concurrent, (int, float))
            and threshold >= max_concurrent):
        warnings.append(
            f"[daemon] generate_threshold ({threshold}) >= max_concurrent ({max_concurrent}) — "
            "new topics will never be generated because active count will always meet threshold"
        )

    # 5. auto_approve.policy must be a known value
    aa_cfg = cfg.get("auto_approve", {})
    policy = aa_cfg.get("policy", "review")
    if policy not in ("review", "verification_sufficient"):
        warnings.append(
            f"[auto_approve] policy = \"{policy}\" — unknown policy; "
            "expected \"review\" or \"verification_sufficient\""
        )

    # 6. verification_sufficient without on_done is likely misconfigured
    if policy == "verification_sufficient":
        verify_cfg = cfg.get("verification", {})
        if not verify_cfg.get("on_done"):
            warnings.append(
                "[auto_approve] policy = \"verification_sufficient\" but "
                "[verification] on_done is not set — explorations without "
                "per-exploration verify_cmd will fall through to AI review"
            )

    # 7. hooks referencing events that don't exist
    hooks_cfg = cfg.get("hooks", {})
    valid_events = {"on_done", "pre_approve", "post_approve", "model", "max_turns"}
    for key in hooks_cfg:
        if key not in valid_events:
            warnings.append(
                f"[hooks] unknown key \"{key}\" — valid lifecycle events: "
                "on_done, pre_approve, post_approve"
            )

    # 8. verification.max_retries should be >= 0
    verify_cfg = cfg.get("verification", {})
    max_retries = verify_cfg.get("max_retries", 2)
    if isinstance(max_retries, (int, float)) and max_retries < 0:
        warnings.append(
            f"[verification] max_retries = {max_retries} — must be >= 0"
        )

    # 9. session.pending_ttl_days should be > 0 if set
    session_cfg = cfg.get("session", {})
    ttl = session_cfg.get("pending_ttl_days")
    if ttl is not None and isinstance(ttl, (int, float)) and ttl <= 0:
        warnings.append(
            f"[session] pending_ttl_days = {ttl} — must be > 0 (or remove to disable)"
        )

    return warnings


def register_project(project_dir: Path) -> None:
    """Register a project in the global ~/.elmer/projects.json registry."""
    GLOBAL_DIR.mkdir(exist_ok=True)
    projects = _load_registry()
    path_str = str(project_dir.resolve())
    if path_str not in projects:
        projects.append(path_str)
        _save_registry(projects)


def list_registered_projects() -> list[Path]:
    """Return all registered project directories that still have .elmer/."""
    projects = _load_registry()
    valid = []
    for p in projects:
        path = Path(p)
        if (path / ".elmer").exists():
            valid.append(path)
    # Prune stale entries
    if len(valid) != len(projects):
        _save_registry([str(p) for p in valid])
    return valid


def _load_registry() -> list[str]:
    """Load the project registry from disk."""
    if not PROJECTS_REGISTRY.exists():
        return []
    try:
        return json.loads(PROJECTS_REGISTRY.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_registry(projects: list[str]) -> None:
    """Save the project registry to disk."""
    GLOBAL_DIR.mkdir(exist_ok=True)
    PROJECTS_REGISTRY.write_text(json.dumps(projects, indent=2) + "\n")


def resolve_archetype(elmer_dir: Path, archetype_name: str) -> Path:
    """Find an archetype template file. Checks project .elmer/ first, then bundled."""
    # Project-local archetype
    local = elmer_dir / "archetypes" / f"{archetype_name}.md"
    if local.exists():
        return local

    # Bundled archetype
    bundled = ARCHETYPES_DIR / f"{archetype_name}.md"
    if bundled.exists():
        return bundled

    raise FileNotFoundError(
        f"Archetype '{archetype_name}' not found in .elmer/archetypes/ or bundled archetypes"
    )


# ---------------------------------------------------------------------------
# Agent definitions — Claude Code subagent integration
# ---------------------------------------------------------------------------

def parse_agent_file(content: str) -> tuple[dict, str]:
    """Parse a markdown file with YAML frontmatter.

    Returns (metadata, body) where metadata is a dict of key-value pairs
    and body is the markdown content after the frontmatter.
    Handles simple YAML: string values, comma-separated lists.
    """
    if not content.startswith("---"):
        return {}, content.strip()

    try:
        end = content.index("---", 3)
    except ValueError:
        return {}, content.strip()

    frontmatter = content[3:end].strip()
    body = content[end + 3:].strip()

    metadata: dict = {}
    for line in frontmatter.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # Comma-separated values become lists (for tools field)
        if "," in value:
            value = [v.strip() for v in value.split(",")]
        metadata[key] = value

    return metadata, body


def resolve_agent(project_dir: Path, archetype_name: str) -> dict | None:
    """Build a Claude Code agent config dict for an archetype.

    Resolution order:
    1. Project-local .claude/agents/elmer-<name>.md
    2. Bundled src/elmer/agents/<name>.md

    Returns a dict suitable for --agents JSON:
        {"name": str, "description": str, "prompt": str, "tools": list, "model": str}
    Returns None if no agent definition exists for this archetype.
    """
    # Determine the agent filename and expected name
    agent_name = f"{AGENT_PREFIX}{archetype_name}"
    agent_filename = f"{agent_name}.md"

    # Check project-local first
    local_path = project_dir / ".claude" / "agents" / agent_filename
    if local_path.exists():
        content = local_path.read_text()
    else:
        # Check bundled agents
        bundled_path = AGENTS_DIR / f"{archetype_name}.md"
        if not bundled_path.exists():
            return None
        content = bundled_path.read_text()

    metadata, body = parse_agent_file(content)
    if not body:
        return None

    config = {
        "name": metadata.get("name", agent_name),
        "description": metadata.get("description", f"Elmer {archetype_name} agent"),
        "prompt": body,
    }

    # Optional fields
    tools = metadata.get("tools")
    if tools:
        config["tools"] = tools if isinstance(tools, list) else [tools]
    model = metadata.get("model")
    if model:
        config["model"] = model

    return config


def resolve_meta_agent(project_dir: Path, meta_name: str) -> dict | None:
    """Build a Claude Code agent config dict for a meta-operation.

    Same resolution as resolve_agent but for meta-operation agents
    (generate-topics, review-gate, select-archetype, etc.).
    """
    agent_name = f"{META_AGENT_PREFIX}{meta_name}"
    agent_filename = f"{agent_name}.md"

    # Check project-local first
    local_path = project_dir / ".claude" / "agents" / agent_filename
    if local_path.exists():
        content = local_path.read_text()
    else:
        bundled_path = AGENTS_DIR / f"{meta_name}.md"
        if not bundled_path.exists():
            return None
        content = bundled_path.read_text()

    metadata, body = parse_agent_file(content)
    if not body:
        return None

    config = {
        "name": metadata.get("name", agent_name),
        "description": metadata.get("description", f"Elmer meta {meta_name} agent"),
        "prompt": body,
    }

    tools = metadata.get("tools")
    if tools:
        config["tools"] = tools if isinstance(tools, list) else [tools]
    model = metadata.get("model")
    if model:
        config["model"] = model

    return config


def list_bundled_agents() -> list[Path]:
    """List all bundled agent definition files."""
    if not AGENTS_DIR.exists():
        return []
    return sorted(AGENTS_DIR.glob("*.md"))


# ---------------------------------------------------------------------------
# Skill resolution — Claude Code project skills (.claude/skills/)
# ---------------------------------------------------------------------------

def resolve_skill(project_dir: Path, skill_name: str) -> dict | None:
    """Load a Claude Code skill from .claude/skills/<name>/SKILL.md.

    Returns a dict with 'name', 'description', 'prompt' (the skill body),
    or None if the skill doesn't exist.

    Skills use YAML frontmatter (name, description, argument-hint) and
    a markdown body with $ARGUMENTS substitution (ADR-064).
    """
    skill_path = project_dir / ".claude" / "skills" / skill_name / "SKILL.md"
    if not skill_path.exists():
        return None

    content = skill_path.read_text()
    metadata, body = parse_agent_file(content)
    if not body:
        return None

    return {
        "name": metadata.get("name", skill_name),
        "description": metadata.get("description", f"Skill: {skill_name}"),
        "prompt": body,
        "argument_hint": metadata.get("argument-hint", ""),
    }


def list_project_skills(project_dir: Path) -> list[str]:
    """List all skills available in a project's .claude/skills/ directory."""
    skills_dir = project_dir / ".claude" / "skills"
    if not skills_dir.exists():
        return []
    return sorted(
        d.name for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


def get_hook_skills(elmer_dir: Path) -> dict[str, list[str]]:
    """Load skill hook configuration from [hooks] section.

    Returns a dict mapping lifecycle events to lists of skill names:
        {"on_done": ["mission-align"], "pre_approve": ["cultural-lens"]}
    """
    cfg = load_config(elmer_dir)
    hooks = cfg.get("hooks", {})
    result: dict[str, list[str]] = {}
    for event in ("on_done", "pre_approve", "post_approve"):
        skills = hooks.get(event, [])
        if isinstance(skills, str):
            skills = [skills]
        if skills:
            result[event] = skills
    return result
