"""MCP elmer_archetypes tool tests — verifies local agent discovery (ADR-075).

Guards against the NameError regression where project_dir was discarded
by destructuring _find_project() as `_, elmer_dir` while still being
referenced to find local agents.
"""

from pathlib import Path
from unittest.mock import patch

from elmer.mcp_server import elmer_archetypes


class TestElmerArchetypes:
    """Verify the MCP archetypes tool lists bundled + local agents."""

    def test_lists_bundled_agents(self, tmp_path):
        """Without local agents, returns bundled agent names."""
        elmer_dir = tmp_path / ".elmer"
        elmer_dir.mkdir()

        with patch("elmer.mcp_server._find_project", return_value=(tmp_path, elmer_dir)):
            result = elmer_archetypes()

        assert "error" not in result
        names = [a["name"] for a in result["archetypes"]]
        # Spot-check a few known bundled agents
        assert "explore-act" in names
        assert "explore" in names
        assert "devil-advocate" in names
        # All should be bundled source
        for entry in result["archetypes"]:
            assert entry["source"] == "bundled"

    def test_local_agents_override_bundled(self, tmp_path):
        """Project-local agents in .claude/agents/ take precedence."""
        elmer_dir = tmp_path / ".elmer"
        elmer_dir.mkdir()

        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "elmer-explore-act.md").write_text(
            "---\nname: elmer-explore-act\n---\nCustom"
        )

        with patch("elmer.mcp_server._find_project", return_value=(tmp_path, elmer_dir)):
            result = elmer_archetypes()

        assert "error" not in result
        by_name = {a["name"]: a for a in result["archetypes"]}
        assert by_name["explore-act"]["source"] == "project"
        # Other bundled agents still present
        assert by_name["explore"]["source"] == "bundled"

    def test_custom_local_agent_appears(self, tmp_path):
        """A custom agent not in bundled set appears with source=project."""
        elmer_dir = tmp_path / ".elmer"
        elmer_dir.mkdir()

        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "elmer-stakeholder-brief.md").write_text(
            "---\nname: elmer-stakeholder-brief\n---\nCustom archetype"
        )

        with patch("elmer.mcp_server._find_project", return_value=(tmp_path, elmer_dir)):
            result = elmer_archetypes()

        assert "error" not in result
        names = [a["name"] for a in result["archetypes"]]
        assert "stakeholder-brief" in names
        by_name = {a["name"]: a for a in result["archetypes"]}
        assert by_name["stakeholder-brief"]["source"] == "project"
