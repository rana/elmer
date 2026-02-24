Analyze a potential dead end, failed approach, or risky direction.

Read the project's documentation to ground yourself in its actual state.
If CLAUDE.md exists, follow its instructions.
If CONTEXT.md exists, read it for current state.
If DESIGN.md exists, read it for architecture.
If DECISIONS.md exists, read entries for past choices and their rationale.
If ROADMAP.md exists, read it for planned features.

$TOPIC

Investigate whether this direction is a dead end. Look for evidence both
for and against. Consider opportunity cost, technical debt, and alternatives.
The goal is to save the project from investing in unproductive directions —
or to confirm that a seemingly risky direction is actually worth pursuing.

IMPORTANT: You MUST use the Write tool to create a file named PROPOSAL.md in the current working directory. Do not include the full proposal in your response text — write it to the file. Your session is considered failed if PROPOSAL.md does not exist on disk when you finish.

Write your analysis to PROPOSAL.md with:

## Summary
One-paragraph verdict: dead end, viable, or uncertain.

## The Case For
Strongest arguments that this direction is worth pursuing.
Evidence from the codebase, docs, or domain knowledge.

## The Case Against
Strongest arguments that this is a dead end or bad investment.
Red flags, technical blockers, opportunity cost.

## Evidence Examined
What you actually looked at — files, patterns, decisions, external references.

## Verdict
Your recommendation with confidence level (high / medium / low).

## If Proceeding
What to watch for. Milestones that would confirm or refute viability.
Exit criteria — when to stop if it's not working.

## If Abandoning
What to salvage. Lessons learned. Alternative directions worth exploring instead.

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
