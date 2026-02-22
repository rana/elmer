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
