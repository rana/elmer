"""Tests for B1: amend failure pattern detection (ADR-050).

Verifies that _is_repeated_failure() correctly detects identical verification
outputs across amend attempts, enabling fail-fast for systemic issues.
"""

from pathlib import Path

import pytest

from elmer.review import _is_repeated_failure


class TestIsRepeatedFailure:
    """Tests for _is_repeated_failure()."""

    def test_first_failure_stores_output(self, elmer_dir):
        """First failure returns False and stores the output."""
        result = _is_repeated_failure(elmer_dir, "test-exp", "npm test failed\nError: missing module")
        assert result is False

        verify_path = elmer_dir / "logs" / "test-exp.verify"
        assert verify_path.exists()
        assert "npm test failed" in verify_path.read_text()

    def test_identical_failure_detected(self, elmer_dir):
        """Second identical failure returns True."""
        output = "npm test failed\nError: missing module 'foo'"
        _is_repeated_failure(elmer_dir, "test-exp", output)  # Store first
        result = _is_repeated_failure(elmer_dir, "test-exp", output)  # Compare
        assert result is True

    def test_different_failure_not_detected(self, elmer_dir):
        """Different failure output returns False and updates stored output."""
        _is_repeated_failure(elmer_dir, "test-exp", "Error: missing module 'foo'")
        result = _is_repeated_failure(elmer_dir, "test-exp", "Error: type mismatch in bar.ts")
        assert result is False

        # Stored output should be the new one
        verify_path = elmer_dir / "logs" / "test-exp.verify"
        assert "type mismatch" in verify_path.read_text()

    def test_whitespace_normalized(self, elmer_dir):
        """Leading/trailing whitespace doesn't affect comparison."""
        _is_repeated_failure(elmer_dir, "test-exp", "  Error: foo  \n")
        result = _is_repeated_failure(elmer_dir, "test-exp", "\n  Error: foo  ")
        assert result is True

    def test_long_output_truncated(self, elmer_dir):
        """Only first 500 chars are compared."""
        base = "x" * 500
        output1 = base + "AAAAAAA"
        output2 = base + "BBBBBBB"
        _is_repeated_failure(elmer_dir, "test-exp", output1)
        result = _is_repeated_failure(elmer_dir, "test-exp", output2)
        assert result is True  # First 500 chars are identical

    def test_different_explorations_independent(self, elmer_dir):
        """Different exploration IDs have independent tracking."""
        output = "Error: foo"
        _is_repeated_failure(elmer_dir, "exp-a", output)
        result = _is_repeated_failure(elmer_dir, "exp-b", output)
        assert result is False  # First time for exp-b
