"""Key-files flow validation tests — semantic plan pre-flight (ADR-076).

Verifies that validate_key_files_flow() catches:
- Orphaned producers (key_files declared but no dependent step)
- Missing dependencies (shared key_file without dependency chain)
"""

from elmer.decompose import validate_key_files_flow


class TestValidateKeyFilesFlow:
    """Verify key_files dependency flow validation."""

    def test_empty_plan_passes(self):
        """Empty plan produces no warnings."""
        assert validate_key_files_flow({"steps": []}) == []
        assert validate_key_files_flow({}) == []

    def test_no_key_files_passes(self):
        """Plan with no key_files is always valid."""
        plan = {"steps": [
            {"topic": "step 0", "depends_on": []},
            {"topic": "step 1", "depends_on": [0]},
        ]}
        assert validate_key_files_flow(plan) == []

    def test_well_wired_plan_passes(self):
        """Plan where key_files producers are properly depended upon."""
        plan = {"steps": [
            {"topic": "scaffold", "depends_on": [], "key_files": ["package.json"]},
            {"topic": "implement", "depends_on": [0], "key_files": ["src/app.ts"]},
            {"topic": "test", "depends_on": [1], "key_files": []},
        ]}
        assert validate_key_files_flow(plan) == []

    def test_orphaned_producer_warns(self):
        """Step with key_files but no dependents triggers warning."""
        plan = {"steps": [
            {"topic": "scaffold", "depends_on": [], "key_files": ["package.json"]},
            {"topic": "unrelated", "depends_on": [], "key_files": []},
        ]}
        warnings = validate_key_files_flow(plan)
        assert len(warnings) == 1
        assert "step 0" in warnings[0]
        assert "no later step depends on it" in warnings[0]

    def test_last_step_key_files_no_warning(self):
        """Last step naturally has no dependents — no orphan warning."""
        plan = {"steps": [
            {"topic": "scaffold", "depends_on": []},
            {"topic": "final", "depends_on": [0], "key_files": ["output.md"]},
        ]}
        assert validate_key_files_flow(plan) == []

    def test_shared_key_file_without_dependency_warns(self):
        """Two steps declaring same key_file without dependency chain."""
        plan = {"steps": [
            {"topic": "scaffold", "depends_on": [], "key_files": ["config.ts"]},
            {"topic": "other", "depends_on": [], "key_files": ["config.ts"]},
            {"topic": "final", "depends_on": [0, 1]},
        ]}
        warnings = validate_key_files_flow(plan)
        assert any("config.ts" in w and "doesn't depend on it" in w
                    for w in warnings)

    def test_shared_key_file_with_dependency_ok(self):
        """Two steps declaring same key_file with proper dependency chain."""
        plan = {"steps": [
            {"topic": "create config", "depends_on": [], "key_files": ["config.ts"]},
            {"topic": "update config", "depends_on": [0], "key_files": ["config.ts"]},
            {"topic": "use config", "depends_on": [1]},
        ]}
        # Step 1 depends on step 0, so no "doesn't depend on it" warning
        warnings = validate_key_files_flow(plan)
        assert not any("doesn't depend on it" in w for w in warnings)

    def test_transitive_dependency_ok(self):
        """Transitive dependency satisfies key_files flow."""
        plan = {"steps": [
            {"topic": "scaffold", "depends_on": [], "key_files": ["base.py"]},
            {"topic": "middle", "depends_on": [0]},
            {"topic": "final", "depends_on": [1], "key_files": ["base.py"]},
        ]}
        # Step 2 transitively depends on step 0 via step 1
        warnings = validate_key_files_flow(plan)
        assert not any("doesn't depend on it" in w for w in warnings)

    def test_complex_dag_validates(self):
        """Multi-branch DAG with correct key_files wiring."""
        plan = {"steps": [
            {"topic": "scaffold", "depends_on": [], "key_files": ["package.json"]},
            {"topic": "api", "depends_on": [0], "key_files": ["src/api.ts"]},
            {"topic": "ui", "depends_on": [0], "key_files": ["src/app.tsx"]},
            {"topic": "integration", "depends_on": [1, 2], "key_files": []},
        ]}
        assert validate_key_files_flow(plan) == []

    def test_single_step_no_warnings(self):
        """Single-step plan never warns (no flow to validate)."""
        plan = {"steps": [
            {"topic": "everything", "depends_on": [], "key_files": ["all.py"]},
        ]}
        assert validate_key_files_flow(plan) == []
