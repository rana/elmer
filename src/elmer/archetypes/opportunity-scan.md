Scan for emergent opportunities, underexploited capabilities, and hidden simplifications.

Read the project's documentation to ground yourself in its actual state.
If CLAUDE.md exists, follow its instructions.
If CONTEXT.md exists, read it for current state.
If DESIGN.md exists, read it for architecture.
If DECISIONS.md exists, read entries for past choices and their rationale.
If ROADMAP.md exists, read it for planned phases and priorities.

$TOPIC

Look beyond what the project is currently doing:
- What wants to emerge that isn't yet captured?
- Are there underexploited capabilities in the current architecture?
- Are there phase transitions that could be accelerated given current state?
- Are there decisions that should be revisited given what the project now knows?
- Are there simplifications hiding in plain sight?
- What would serve the project's goals that hasn't been considered?
- Are there patterns from adjacent domains that could be applied here?
- Is the project building toward something it hasn't articulated yet?

Propose concrete actions, not just observations. For every insight, specify exactly where it belongs in the project (file, section, identifier).

Write your findings to PROPOSAL.md with:

## Summary
One-paragraph overview of the most significant opportunities found.

## Opportunities
For each opportunity:
### Opportunity: <brief description>
- **What:** The specific capability, simplification, or direction
- **Why now:** What about the current project state makes this timely
- **Impact:** How this would improve the project (velocity / quality / scope)
- **Effort:** What it would take to pursue this
- **Where it belongs:** File, section, ADR, or roadmap item

## Simplifications
Complexity that could be eliminated without losing capability. Each with evidence.

## Revisitable Decisions
Past decisions that may no longer be optimal given what the project now knows.

## Highest-Value Move
The single most impactful action the project could take right now, with full reasoning.
