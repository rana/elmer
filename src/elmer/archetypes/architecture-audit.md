Review architecture patterns in use and identify drift, gaps, or opportunities.

Read the project's documentation to ground yourself in its actual state.
If CLAUDE.md exists, follow its instructions.
If CONTEXT.md exists, read it for current state.
If DESIGN.md exists, read it for architecture.
If DECISIONS.md exists, read all entries — these document the chosen patterns.
If ROADMAP.md exists, read it for planned phases.

Focus area: $TOPIC

Examine architecture patterns:
- Are chosen patterns being applied consistently across the codebase?
- Is loose coupling maintained — or have implicit dependencies crept in?
- Are there emerging patterns in the codebase not captured in ADRs?
- Do new features follow established conventions or diverge silently?
- Are there patterns the project should adopt given its current state?
- Are there patterns adopted early that no longer serve the project?
- Is the abstraction level appropriate — neither over-engineered nor under-structured?
- Are boundaries between components clear and respected?

Focus on what has changed since the last review or what looks fragile.

Write your audit to PROPOSAL.md with:

## Summary
One-paragraph assessment of architectural health in the focus area.

## Pattern Compliance
Patterns that are being followed consistently. Evidence of good discipline.

## Pattern Drift
For each case of drift:
### Drift: <brief description>
- **Expected pattern:** What the architecture calls for
- **Actual behavior:** What the code does instead
- **Where:** File paths and code locations
- **Impact:** How this affects maintainability, correctness, or extensibility
- **Recommendation:** Align code to pattern / update pattern to match reality / new ADR needed

## Emerging Patterns
Patterns appearing in the codebase that aren't formally documented. Should they be?

## Recommended Changes
Ordered list of architectural improvements, from highest to lowest impact.
