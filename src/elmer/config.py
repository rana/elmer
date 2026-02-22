"""Configuration loading and project initialization."""

import shutil
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

ARCHETYPES_DIR = Path(__file__).parent / "archetypes"

DEFAULT_CONFIG = """\
[defaults]
archetype = "explore-act"
model = "sonnet"
max_turns = 50
"""

GITIGNORE = """\
worktrees/
logs/
state.db
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

    return elmer_dir


def load_config(elmer_dir: Path) -> dict:
    """Load .elmer/config.toml, returning defaults if missing."""
    config_path = elmer_dir / "config.toml"
    if config_path.exists():
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    return {"defaults": {"archetype": "explore-act", "model": "sonnet", "max_turns": 50}}


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
