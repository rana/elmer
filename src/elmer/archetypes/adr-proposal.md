Propose an architecture decision for the project.

Read the project's documentation to ground yourself in its actual state.
If CLAUDE.md exists, follow its instructions.
If CONTEXT.md exists, read it for current state.
If DESIGN.md exists, read it for architecture.
If DECISIONS.md exists, read all entries — understand the precedent and style.
If ROADMAP.md exists, read it for planned phases.

$TOPIC

Research this thoroughly. Identify the decision point, enumerate alternatives,
and recommend a specific choice with rationale.

IMPORTANT: You MUST use the Write tool to create a file named PROPOSAL.md in the current working directory. Do not include the full proposal in your response text — write it to the file. Your session is considered failed if PROPOSAL.md does not exist on disk when you finish.

Write your proposal to PROPOSAL.md with:

## Summary
One-paragraph overview of the decision being proposed.

## Context
Why this decision is needed now. What triggered it.

## Alternatives Considered
For each alternative:
- **Option:** What it is
- **Pros:** Advantages
- **Cons:** Disadvantages
- **Precedent:** Where this approach is used successfully (if applicable)

## Recommendation
Your recommended option with detailed rationale.

## Consequences
What changes if this decision is adopted:
- What becomes easier
- What becomes harder
- What new constraints are introduced

## Draft ADR
A ready-to-append ADR entry in the project's existing format.
If DECISIONS.md exists, match its style exactly.

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
