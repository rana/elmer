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

DEFAULT_CONFIG = """\
[defaults]
archetype = "explore-act"
model = "opus"
max_turns = 50
generate_prompt = false
# budget_usd = 2.00           # optional per-exploration budget cap

[generate]
count = 5
model = "sonnet"
max_turns = 5
# budget_usd = 10.00          # optional total budget for generate command

[auto_approve]
model = "sonnet"
max_turns = 3
criteria = "document-only proposals with no code changes"
max_files_changed = 10
require_proposal = true

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
# budget_per_cycle = 5.00       # optional cost cap per cycle (USD)
max_concurrent = 5
generate_threshold = 2          # generate new topics when active < threshold
generate_count = 5

[insights]
enabled = false                 # extract insights after approval
model = "sonnet"
max_turns = 3
inject = true                   # inject cross-project insights into prompts
inject_limit = 5                # max insights to inject per exploration

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
state.db
daemon.pid
"""


def init_project(project_dir: Path) -> Path:
    """Initialize .elmer/ in a project directory."""
    elmer_dir = project_dir / ".elmer"
    elmer_dir.mkdir(exist_ok=True)

    # Config
    config_path = elmer_dir / "config.toml"
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG)

    # Archetypes (copy bundled defaults)
    archetypes_dest = elmer_dir / "archetypes"
    archetypes_dest.mkdir(exist_ok=True)
    for src_file in ARCHETYPES_DIR.glob("*.md"):
        dest_file = archetypes_dest / src_file.name
        if not dest_file.exists():
            shutil.copy2(src_file, dest_file)

    # Working directories
    (elmer_dir / "worktrees").mkdir(exist_ok=True)
    (elmer_dir / "logs").mkdir(exist_ok=True)

    # Gitignore for transient state
    gitignore_path = elmer_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(GITIGNORE)

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
