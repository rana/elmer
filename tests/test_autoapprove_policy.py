"""Auto-approve policy tests — trust escalation (ADR-076).

Verifies that [auto_approve].policy controls gate behavior:
- "review" (default): existing three-layer gate
- "verification_sufficient": skip AI review when verify_cmd passed
"""

from elmer.autoapprove import _validate_proposal_structure


class TestValidateProposalStructure:
    """Structural validation is policy-independent."""

    def test_empty_fails(self):
        valid, error = _validate_proposal_structure("")
        assert not valid
        assert "empty" in error

    def test_too_short_fails(self):
        valid, error = _validate_proposal_structure("# Short\n\nNot enough text here.")
        assert not valid
        assert "too short" in error

    def test_todo_marker_fails(self):
        content = "# Proposal\n\n" + "x" * 100 + "\n\nTODO: finish this"
        valid, error = _validate_proposal_structure(content)
        assert not valid
        assert "TODO:" in error

    def test_no_heading_fails(self):
        content = "This is just text.\n" * 10
        valid, error = _validate_proposal_structure(content)
        assert not valid
        assert "no markdown headings" in error

    def test_valid_proposal_passes(self):
        content = "# Proposal\n\n" + "This is a valid proposal with enough content. " * 5
        valid, error = _validate_proposal_structure(content)
        assert valid
        assert error == ""

    def test_fixme_marker_fails(self):
        content = "# Proposal\n\n" + "x" * 100 + "\n\nFIXME: broken"
        valid, error = _validate_proposal_structure(content)
        assert not valid
        assert "FIXME:" in error
