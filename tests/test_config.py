"""Config contract tests — loading, defaults, agent/skill resolution (ADR-075).

Guards the configuration layer: every command reads config through load_config().
Config parsing mistakes cascade to every module.
"""

import pytest

from elmer.config import (
    DEFAULT_CONFIG,
    load_config,
    parse_agent_file,
    resolve_archetype,
    get_hook_skills,
)


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    """Verify TOML parsing and fallback defaults."""

    def test_missing_config_returns_defaults(self, elmer_dir):
        """When config.toml doesn't exist, return hardcoded defaults."""
        cfg = load_config(elmer_dir)
        assert cfg["defaults"]["archetype"] == "explore-act"
        assert cfg["defaults"]["model"] == "opus"
        assert cfg["defaults"]["max_turns"] == 50

    def test_default_config_parses(self, elmer_dir):
        """The DEFAULT_CONFIG string is valid TOML and parses correctly."""
        (elmer_dir / "config.toml").write_text(DEFAULT_CONFIG)
        cfg = load_config(elmer_dir)
        assert cfg["defaults"]["archetype"] == "explore-act"
        assert cfg["daemon"]["interval"] == 600
        assert cfg["verification"]["max_retries"] == 2
        assert cfg["implement"]["model"] == "opus"

    def test_custom_config(self, elmer_dir):
        """Custom config values override defaults."""
        (elmer_dir / "config.toml").write_text(
            '[defaults]\narchetype = "devil-advocate"\nmodel = "haiku"\nmax_turns = 10\n'
        )
        cfg = load_config(elmer_dir)
        assert cfg["defaults"]["archetype"] == "devil-advocate"
        assert cfg["defaults"]["model"] == "haiku"
        assert cfg["defaults"]["max_turns"] == 10

    def test_partial_config(self, elmer_dir):
        """Config with only some sections still loads."""
        (elmer_dir / "config.toml").write_text('[daemon]\ninterval = 300\n')
        cfg = load_config(elmer_dir)
        assert cfg["daemon"]["interval"] == 300
        # Other sections are absent (not filled from defaults)
        assert "defaults" not in cfg

    def test_nested_table(self, elmer_dir):
        """Nested TOML tables like [costs.rates] parse correctly."""
        (elmer_dir / "config.toml").write_text(
            '[costs.rates]\nhaiku_input = 0.50\n'
        )
        cfg = load_config(elmer_dir)
        assert cfg["costs"]["rates"]["haiku_input"] == 0.50

    def test_all_default_sections_present(self, elmer_dir):
        """DEFAULT_CONFIG has all expected top-level sections."""
        (elmer_dir / "config.toml").write_text(DEFAULT_CONFIG)
        cfg = load_config(elmer_dir)
        expected = {"defaults", "generate", "auto_approve", "archetype_selection",
                    "followup", "daemon", "insights", "ensemble", "digest",
                    "questions", "invariants", "audit", "session", "hooks",
                    "verification", "implement", "costs"}
        assert expected.issubset(set(cfg.keys())), f"Missing: {expected - set(cfg.keys())}"


# ---------------------------------------------------------------------------
# parse_agent_file
# ---------------------------------------------------------------------------

class TestParseAgentFile:
    """Verify YAML frontmatter parsing from agent markdown files."""

    def test_no_frontmatter(self):
        metadata, body = parse_agent_file("Just a body\nWith lines")
        assert metadata == {}
        assert body == "Just a body\nWith lines"

    def test_basic_frontmatter(self):
        content = "---\nname: test-agent\ndescription: A test\n---\nBody here"
        metadata, body = parse_agent_file(content)
        assert metadata["name"] == "test-agent"
        assert metadata["description"] == "A test"
        assert body == "Body here"

    def test_comma_separated_values(self):
        """Comma-separated values in frontmatter become lists."""
        content = "---\ntools: Read, Grep, Glob\n---\nBody"
        metadata, body = parse_agent_file(content)
        assert metadata["tools"] == ["Read", "Grep", "Glob"]

    def test_empty_body(self):
        content = "---\nname: empty\n---\n"
        metadata, body = parse_agent_file(content)
        assert metadata["name"] == "empty"
        assert body == ""

    def test_unclosed_frontmatter(self):
        """Missing closing --- treats everything as body."""
        content = "---\nname: broken\nBody text"
        metadata, body = parse_agent_file(content)
        assert metadata == {}

    def test_comments_ignored(self):
        content = "---\n# comment\nname: real\n---\nBody"
        metadata, body = parse_agent_file(content)
        assert "# comment" not in metadata
        assert metadata["name"] == "real"


# ---------------------------------------------------------------------------
# resolve_archetype
# ---------------------------------------------------------------------------

class TestResolveArchetype:
    """Verify archetype resolution priority: local > bundled."""

    def test_bundled_archetype_found(self, elmer_dir):
        """Bundled archetypes resolve from the package's archetypes directory."""
        # 'explore' should exist as a bundled archetype
        path = resolve_archetype(elmer_dir, "explore")
        assert path.exists()
        assert path.name == "explore.md"

    def test_local_archetype_priority(self, elmer_dir):
        """Project-local archetype takes priority over bundled."""
        local_dir = elmer_dir / "archetypes"
        local_dir.mkdir()
        local_file = local_dir / "explore.md"
        local_file.write_text("# Custom explore")
        path = resolve_archetype(elmer_dir, "explore")
        assert path == local_file

    def test_nonexistent_archetype_raises(self, elmer_dir):
        with pytest.raises(FileNotFoundError, match="not-a-real-archetype"):
            resolve_archetype(elmer_dir, "not-a-real-archetype")


# ---------------------------------------------------------------------------
# get_hook_skills
# ---------------------------------------------------------------------------

class TestGetHookSkills:
    """Verify skill hook configuration parsing."""

    def test_no_hooks(self, elmer_dir):
        (elmer_dir / "config.toml").write_text('[hooks]\nmodel = "sonnet"\n')
        result = get_hook_skills(elmer_dir)
        assert result == {}

    def test_list_hooks(self, elmer_dir):
        (elmer_dir / "config.toml").write_text(
            '[hooks]\non_done = ["mission-align", "quality-check"]\n'
        )
        result = get_hook_skills(elmer_dir)
        assert result["on_done"] == ["mission-align", "quality-check"]

    def test_string_hook_becomes_list(self, elmer_dir):
        (elmer_dir / "config.toml").write_text(
            '[hooks]\npre_approve = "cultural-lens"\n'
        )
        result = get_hook_skills(elmer_dir)
        assert result["pre_approve"] == ["cultural-lens"]
