"""Retry policy tests — failure-aware daemon retry (ADR-076).

Verifies that get_retry_policy() returns correct policy for each failure
category, and that the RETRY_POLICY dict covers all FAILURE_* constants.
"""

from elmer.review import (
    FAILURE_BRANCH_CONFLICT,
    FAILURE_CLAUDE_ERROR,
    FAILURE_DEPENDENCY_FAILED,
    FAILURE_EMPTY_LOG,
    FAILURE_LOG_CORRUPT,
    FAILURE_NO_LOG,
    FAILURE_NO_PROPOSAL,
    FAILURE_PERMISSION_DENIED,
    FAILURE_PROPOSAL_MISSING,
    FAILURE_STALE_PENDING,
    FAILURE_VERIFICATION_EXHAUSTED,
    FAILURE_VERIFICATION_FAILED,
    FAILURE_WRONG_PATH,
    RETRY_POLICY,
    get_retry_policy,
)


class TestRetryPolicyCompleteness:
    """Verify RETRY_POLICY covers all failure categories."""

    def test_all_failure_constants_covered(self):
        """Every FAILURE_* constant has a policy entry."""
        all_categories = {
            FAILURE_NO_LOG, FAILURE_EMPTY_LOG, FAILURE_LOG_CORRUPT,
            FAILURE_CLAUDE_ERROR, FAILURE_WRONG_PATH, FAILURE_PROPOSAL_MISSING,
            FAILURE_PERMISSION_DENIED, FAILURE_NO_PROPOSAL,
            FAILURE_VERIFICATION_FAILED, FAILURE_VERIFICATION_EXHAUSTED,
            FAILURE_STALE_PENDING, FAILURE_DEPENDENCY_FAILED,
            FAILURE_BRANCH_CONFLICT,
        }
        assert set(RETRY_POLICY.keys()) == all_categories

    def test_all_policies_are_valid_values(self):
        """Every policy value is one of the three allowed strings."""
        valid = {"retry", "retry_with_context", "skip"}
        for category, policy in RETRY_POLICY.items():
            assert policy in valid, f"{category} has invalid policy: {policy}"


class TestGetRetryPolicy:
    """Verify get_retry_policy() returns correct policy."""

    def test_transient_failures_are_retriable(self):
        """Transient failures (infrastructure issues) should be retried."""
        for cat in [FAILURE_NO_LOG, FAILURE_EMPTY_LOG, FAILURE_LOG_CORRUPT,
                    FAILURE_CLAUDE_ERROR]:
            assert get_retry_policy(cat) == "retry", f"{cat} should be 'retry'"

    def test_agent_errors_retry_with_context(self):
        """Agent errors should be retried with enhanced failure context."""
        for cat in [FAILURE_WRONG_PATH, FAILURE_PROPOSAL_MISSING,
                    FAILURE_NO_PROPOSAL]:
            assert get_retry_policy(cat) == "retry_with_context", \
                f"{cat} should be 'retry_with_context'"

    def test_permanent_failures_are_skipped(self):
        """Permanent failures should never be automatically retried."""
        for cat in [FAILURE_PERMISSION_DENIED, FAILURE_VERIFICATION_FAILED,
                    FAILURE_VERIFICATION_EXHAUSTED, FAILURE_STALE_PENDING,
                    FAILURE_DEPENDENCY_FAILED, FAILURE_BRANCH_CONFLICT]:
            assert get_retry_policy(cat) == "skip", f"{cat} should be 'skip'"

    def test_none_category_returns_retry_with_context(self):
        """Pre-taxonomy failures (None category) default to retry_with_context."""
        assert get_retry_policy(None) == "retry_with_context"

    def test_unknown_category_returns_retry_with_context(self):
        """Unknown categories default to retry_with_context (conservative)."""
        assert get_retry_policy("unknown_category_xyz") == "retry_with_context"
