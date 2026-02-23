"""Batch exploration from topic list files.

Topic list files are markdown documents with --- separators.
Each section between separators is one topic. The filename stem
determines the archetype (e.g., explore-act.md → explore-act).

File format:
    # Optional header (ignored — anything before first ---)

    ---

    First topic text (can be multi-line)

    ---

    Second topic text

    ---
"""

from pathlib import Path


def parse_topic_file(path: Path) -> list[str]:
    """Parse a ---separated topic list file into a list of topic strings.

    Rules:
    - Split on --- (markdown thematic break)
    - Trim whitespace from each section
    - Discard empty sections
    - Discard the first section if it starts with # (header/comments)
    - Each remaining section is one topic (multi-line preserved)
    """
    text = path.read_text()
    sections = text.split("---")

    topics: list[str] = []
    for i, section in enumerate(sections):
        stripped = section.strip()
        if not stripped:
            continue
        # First non-empty section: skip if it's a header
        if i == 0 and stripped.startswith("#"):
            continue
        topics.append(stripped)

    return topics


def archetype_from_filename(path: Path) -> str:
    """Extract archetype name from a topic list file path.

    .elmer/explore-act.md → explore-act
    .elmer/prototype.md   → prototype
    """
    return path.stem
