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

IMPORTANT: You MUST use the Write tool to create a file named PROPOSAL.md in the current working directory. Do not include the full proposal in your response text — write it to the file. Your session is considered failed if PROPOSAL.md does not exist on disk when you finish.

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

## Output Management

**Write early, write often.** Create PROPOSAL.md with a skeleton structure after your initial analysis. Fill sections incrementally as you work. Do not accumulate your entire analysis in memory before writing — if your session ends unexpectedly, the file must exist with whatever you have so far.

**Document reading strategy:**
- CLAUDE.md and CONTEXT.md: read fully (orientation documents).
- DESIGN.md: read sections relevant to your topic. Skip unrelated modules.
- DECISIONS.md: skim headings or index first. Only read specific entries relevant to your topic.
- ROADMAP.md: skim for current state. Skip completed phase details.

**Scope control:**
- If analysis is extensive, deliver highest-priority findings first.
- Keep output concise — dense observations, not expansive prose.
