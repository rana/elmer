"""Config validation tests — interdependency checking (ADR-076).

Verifies that validate_config() catches common misconfigurations
and returns helpful warning messages.
"""

from elmer.config import validate_config


class TestValidateConfig:
    """Verify config validation catches interdependency issues."""

    def test_clean_config_passes(self):
        """A well-formed config produces no warnings."""
        cfg = {
            "defaults": {"archetype": "explore-act", "model": "opus"},
            "daemon": {"auto_approve": True, "max_concurrent": 5, "generate_threshold": 2},
            "auto_approve": {"model": "sonnet", "policy": "review"},
            "generate": {"count": 5, "model": "sonnet"},
            "verification": {"max_retries": 2},
            "session": {"pending_ttl_days": 7},
        }
        assert validate_config(cfg) == []

    def test_daemon_auto_approve_without_section(self):
        """Warn when daemon.auto_approve is true but [auto_approve] missing."""
        cfg = {
            "daemon": {"auto_approve": True, "max_concurrent": 5},
        }
        warnings = validate_config(cfg)
        assert any("[auto_approve] section is missing" in w for w in warnings)

    def test_daemon_auto_generate_without_section(self):
        """Warn when daemon.auto_generate is true but [generate] missing."""
        cfg = {
            "daemon": {"auto_generate": True, "max_concurrent": 5},
        }
        warnings = validate_config(cfg)
        assert any("[generate] section is missing" in w for w in warnings)

    def test_max_concurrent_zero(self):
        """Warn when max_concurrent is < 1."""
        cfg = {"daemon": {"max_concurrent": 0}}
        warnings = validate_config(cfg)
        assert any("max_concurrent" in w and ">= 1" in w for w in warnings)

    def test_generate_threshold_ge_max_concurrent(self):
        """Warn when threshold >= max_concurrent (topics never generated)."""
        cfg = {"daemon": {"generate_threshold": 5, "max_concurrent": 5}}
        warnings = validate_config(cfg)
        assert any("never be generated" in w for w in warnings)

    def test_unknown_policy(self):
        """Warn when policy is not a recognized value."""
        cfg = {"auto_approve": {"policy": "yolo"}}
        warnings = validate_config(cfg)
        assert any("unknown policy" in w for w in warnings)

    def test_verification_sufficient_without_on_done(self):
        """Warn when verification_sufficient but no global verify command."""
        cfg = {
            "auto_approve": {"policy": "verification_sufficient"},
            "verification": {"max_retries": 2},
        }
        warnings = validate_config(cfg)
        assert any("on_done is not set" in w for w in warnings)

    def test_verification_sufficient_with_on_done_ok(self):
        """No warning when verification_sufficient has global verify."""
        cfg = {
            "auto_approve": {"policy": "verification_sufficient"},
            "verification": {"on_done": "npm test", "max_retries": 2},
        }
        warnings = validate_config(cfg)
        assert not any("on_done" in w for w in warnings)

    def test_negative_max_retries(self):
        """Warn when max_retries is negative."""
        cfg = {"verification": {"max_retries": -1}}
        warnings = validate_config(cfg)
        assert any("max_retries" in w and ">= 0" in w for w in warnings)

    def test_zero_pending_ttl(self):
        """Warn when pending_ttl_days is <= 0."""
        cfg = {"session": {"pending_ttl_days": 0}}
        warnings = validate_config(cfg)
        assert any("pending_ttl_days" in w for w in warnings)

    def test_empty_config_passes(self):
        """Empty config (no sections) produces no warnings."""
        assert validate_config({}) == []

    def test_daemon_auto_approve_false_no_warning(self):
        """No warning when daemon.auto_approve is false."""
        cfg = {"daemon": {"auto_approve": False}}
        assert validate_config(cfg) == []

    def test_review_policy_is_valid(self):
        """Default 'review' policy produces no warnings."""
        cfg = {"auto_approve": {"policy": "review"}}
        assert validate_config(cfg) == []

    def test_verification_sufficient_policy_is_valid(self):
        """'verification_sufficient' with on_done produces no warnings."""
        cfg = {
            "auto_approve": {"policy": "verification_sufficient"},
            "verification": {"on_done": "make test"},
        }
        assert validate_config(cfg) == []
