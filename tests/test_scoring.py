"""Scoring and frontmatter tests — proposal parsing, verdict parsing (ADR-075).

Guards the review layer: frontmatter extraction feeds into prioritization
scoring and auto-approve decisions. Parse errors = wrong review order.
"""

import pytest

from elmer.review import parse_proposal_frontmatter
from elmer.autoapprove import _validate_proposal_structure, _parse_verdict, _count_files_in_diff


# ---------------------------------------------------------------------------
# parse_proposal_frontmatter (H2)
# ---------------------------------------------------------------------------

class TestParseProposalFrontmatter:
    """Verify YAML frontmatter extraction from PROPOSAL.md."""

    def test_no_frontmatter(self):
        metadata, body = parse_proposal_frontmatter("# Proposal\n\nContent here")
        assert metadata == {}
        assert body == "# Proposal\n\nContent here"

    def test_basic_frontmatter(self):
        content = "---\ntype: feature\nconfidence: high\n---\n# Proposal"
        metadata, body = parse_proposal_frontmatter(content)
        assert metadata["type"] == "feature"
        assert metadata["confidence"] == "high"
        assert body == "# Proposal"

    def test_list_field(self):
        content = "---\nkey_files: [src/foo.py, src/bar.py]\n---\nBody"
        metadata, body = parse_proposal_frontmatter(content)
        assert metadata["key_files"] == ["src/foo.py", "src/bar.py"]

    def test_empty_list(self):
        content = "---\nkey_files: []\n---\nBody"
        metadata, body = parse_proposal_frontmatter(content)
        assert metadata["key_files"] == []

    def test_boolean_fields(self):
        content = "---\ndecision_needed: true\nblocking: false\n---\nBody"
        metadata, body = parse_proposal_frontmatter(content)
        assert metadata["decision_needed"] is True
        assert metadata["blocking"] is False

    def test_quoted_list_items(self):
        content = "---\nkey_files: ['src/foo.py', \"src/bar.py\"]\n---\nBody"
        metadata, body = parse_proposal_frontmatter(content)
        assert metadata["key_files"] == ["src/foo.py", "src/bar.py"]

    def test_unclosed_frontmatter(self):
        content = "---\ntype: broken\nBody text"
        metadata, body = parse_proposal_frontmatter(content)
        assert metadata == {}

    def test_empty_content(self):
        metadata, body = parse_proposal_frontmatter("")
        assert metadata == {}
        assert body == ""

    def test_frontmatter_only(self):
        content = "---\ntype: note\n---\n"
        metadata, body = parse_proposal_frontmatter(content)
        assert metadata["type"] == "note"
        assert body == ""


# ---------------------------------------------------------------------------
# _validate_proposal_structure (ADR-041)
# ---------------------------------------------------------------------------

class TestValidateProposalStructure:
    """Verify structural validation catches malformed proposals."""

    def test_empty_proposal(self):
        valid, error = _validate_proposal_structure("")
        assert valid is False
        assert "empty" in error

    def test_whitespace_only(self):
        valid, error = _validate_proposal_structure("   \n  \n  ")
        assert valid is False
        assert "empty" in error

    def test_too_short(self):
        valid, error = _validate_proposal_structure("# Short\nToo brief")
        assert valid is False
        assert "too short" in error

    def test_no_headings(self):
        content = "x" * 200  # Long enough, but no markdown headings
        valid, error = _validate_proposal_structure(content)
        assert valid is False
        assert "no markdown headings" in error

    def test_todo_marker(self):
        content = "# Proposal\n\n" + "x" * 100 + "\nTODO: finish this"
        valid, error = _validate_proposal_structure(content)
        assert valid is False
        assert "TODO:" in error

    def test_fixme_marker(self):
        content = "# Proposal\n\n" + "x" * 100 + "\nFIXME: broken thing"
        valid, error = _validate_proposal_structure(content)
        assert valid is False
        assert "FIXME:" in error

    def test_valid_proposal(self):
        content = "# Proposal\n\n## Summary\n\n" + "x" * 200
        valid, error = _validate_proposal_structure(content)
        assert valid is True
        assert error == ""


# ---------------------------------------------------------------------------
# _parse_verdict
# ---------------------------------------------------------------------------

class TestParseVerdict:
    """Verify AI review verdict parsing."""

    def test_approve(self):
        verdict, reason = _parse_verdict("VERDICT: APPROVE — looks good")
        assert verdict == "approve"
        assert reason == "looks good"

    def test_reject(self):
        verdict, reason = _parse_verdict("VERDICT: REJECT — needs work")
        assert verdict == "reject"
        assert reason == "needs work"

    def test_case_insensitive(self):
        verdict, _ = _parse_verdict("verdict: approve — ok")
        assert verdict == "approve"

    def test_dashes_separator(self):
        verdict, reason = _parse_verdict("VERDICT: APPROVE -- all good")
        assert verdict == "approve"
        assert reason == "all good"

    def test_no_verdict_line(self):
        verdict, reason = _parse_verdict("No clear verdict here\nJust text")
        assert verdict == "reject"
        assert "could not parse" in reason

    def test_verdict_among_other_lines(self):
        text = "Analysis complete.\n\nVERDICT: APPROVE — meets criteria\n\nEnd."
        verdict, reason = _parse_verdict(text)
        assert verdict == "approve"


# ---------------------------------------------------------------------------
# _count_files_in_diff
# ---------------------------------------------------------------------------

class TestCountFilesInDiff:
    """Verify diff stat file counting."""

    def test_empty_diff(self):
        assert _count_files_in_diff("") == 0

    def test_typical_diff(self):
        diff = (
            " src/foo.py | 10 +++++\n"
            " src/bar.py |  3 ---\n"
            " 2 files changed, 10 insertions(+), 3 deletions(-)\n"
        )
        assert _count_files_in_diff(diff) == 2

    def test_single_file(self):
        diff = " README.md | 1 +\n 1 file changed, 1 insertion(+)\n"
        assert _count_files_in_diff(diff) == 1
