Audit documentation practices, conventions, and structural quality.

Read the project's documentation to ground yourself in its actual state.
If CLAUDE.md exists, follow its instructions — and audit whether they are being followed.
If CONTEXT.md exists, read it for current state.
If DESIGN.md exists, read it for architecture.
If DECISIONS.md exists, read all entries.
If ROADMAP.md exists, read it for planned phases.

$TOPIC

Examine documentation health:
- Are documented maintenance protocols being followed in practice?
- Are "Status: Implemented" or equivalent markers being added as features ship?
- Are architectural decisions treated as immutable (superseded, not silently edited)?
- Is the documentation-code transition protocol being respected?
- Would a new contributor understand the project from these documents alone?
- Is there redundancy across documents that risks divergence?
- Are open questions being resolved and tracked, not left to go stale?
- Is the writing clear, specific, and actionable — or vague and aspirational?
- Are conventions (naming, formatting, structure) applied consistently?

Propose improvements to documentation practices, not just content.

Write your audit to PROPOSAL.md with:

## Summary
One-paragraph assessment of documentation practice health.

## Protocol Violations
Documented practices that aren't being followed. For each:
- **Protocol:** What the convention says
- **Violation:** What's actually happening
- **Where:** Specific files and sections
- **Fix:** Restore compliance or update the protocol

## Staleness
Content that has drifted from reality. Specific sections and what needs updating.

## Contributor Readability
Assessment of whether a new contributor could onboard from docs alone. Gaps identified.

## Structural Improvements
Changes to documentation structure, conventions, or protocols that would improve long-term quality.

## Recommended Actions
Ordered list of documentation improvements, from highest to lowest impact.
