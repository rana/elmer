Examine the project from an operational and cost perspective.

Read the project's documentation to ground yourself in its actual state.
If CLAUDE.md exists, follow its instructions.
If CONTEXT.md exists, read it for current state.
If DESIGN.md exists, read it for architecture.
If DECISIONS.md exists, skim entries for operational decisions.
If ROADMAP.md exists, read it for deployment and scaling plans.

Focus area: $TOPIC

Investigate operational readiness:
- Are there gaps between what design documents specify and what operations would need?
- What are the projected operational costs at current architecture? At 10x scale?
- Are error handling, logging, and recovery procedures sufficient?
- Is the build/test/deploy pipeline complete and reliable?
- Can changes be rolled back safely?
- Are there single points of failure?
- Are resource limits, timeouts, and circuit breakers specified where needed?
- Are cost optimization opportunities being captured as the architecture evolves?
- What operational questions is the project not asking?

IMPORTANT: You MUST use the Write tool to create a file named PROPOSAL.md in the current working directory. Do not include the full proposal in your response text — write it to the file. Your session is considered failed if PROPOSAL.md does not exist on disk when you finish.

Write your audit to PROPOSAL.md with:

## Summary
One-paragraph operational readiness assessment for the focus area.

## Operational Gaps
For each gap:
### Gap: <brief description>
- **What's missing:** The operational concern not addressed
- **Risk:** What could go wrong without it
- **Severity:** Critical / Significant / Minor
- **Recommendation:** Specific action to close the gap

## Cost Analysis
Current cost profile and scaling projections. Optimization opportunities.

## Resilience Assessment
Single points of failure, recovery gaps, and rollback readiness.

## What's Solid
Operational aspects that are well-handled. Acknowledge good practices.

## Recommended Actions
Ordered list of operational improvements, from highest to lowest urgency.

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
