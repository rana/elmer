Cross-reference integrity scan across all project documentation.

Read the project's documentation to ground yourself in its actual state.
If CLAUDE.md exists, follow its instructions.
If CONTEXT.md exists, read it for current state.
If DESIGN.md exists, read it for architecture.
If DECISIONS.md exists, read all entries.
If ROADMAP.md exists, read it for planned phases.

$TOPIC

Perform a deep cross-reference integrity check:
- Are there errors, gaps, mis-references, or omissions across documents?
- Are ADR references in design documents still accurate?
- Are phase deliverables in the roadmap reflected in design sections?
- Are open questions still genuinely open (not silently resolved elsewhere)?
- Are identifier conventions applied consistently across all files?
- Are there orphaned references — identifiers mentioned but never defined?
- Are there defined identifiers that are never referenced?
- Does documentation match actual code structure and behavior?
- Is there redundancy across documents that risks divergence?

Propose concrete corrections, not just observations.

IMPORTANT: You MUST use the Write tool to create a file named PROPOSAL.md in the current working directory. Do not include the full proposal in your response text — write it to the file. Your session is considered failed if PROPOSAL.md does not exist on disk when you finish.

Write your audit to PROPOSAL.md with:

## Summary
One-paragraph overview of documentation coherence state.

## Cross-Reference Errors
For each broken reference:
### Error: <brief description>
- **Source:** Where the reference appears (file:section)
- **Target:** What it claims to reference
- **Problem:** Missing target / wrong target / stale content
- **Fix:** Exact correction needed

## Orphaned Content
Identifiers, sections, or concepts that exist but are never referenced. Are they still needed?

## Redundancy Risks
Content duplicated across files that could diverge. Which file should be canonical?

## Integrity Verified
Cross-references and connections that checked out. Coverage assessment.

## Recommended Actions
Ordered list of concrete fixes, from highest to lowest priority.

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
