Trace user and developer workflows end-to-end to find friction, gaps, and dead ends.

Read the project's documentation to ground yourself in its actual state.
If CLAUDE.md exists, follow its instructions.
If CONTEXT.md exists, read it for current state.
If DESIGN.md exists, read it for architecture and user-facing flows.
If DECISIONS.md exists, skim entries for UX or workflow decisions.
If ROADMAP.md exists, read it for planned workflow changes.

Focus on these workflows: $TOPIC

For each workflow you can identify:
1. Trace the complete path from start to finish
2. Identify every decision point, handoff, and state transition
3. Look for friction points, dead ends, missing feedback, or unclear next steps
4. Check whether error paths are handled or silently dropped
5. Verify that the documented workflow matches actual behavior
6. Consider the workflow from the perspective of someone encountering it for the first time

IMPORTANT: You MUST use the Write tool to create a file named PROPOSAL.md in the current working directory. Do not include the full proposal in your response text — write it to the file. Your session is considered failed if PROPOSAL.md does not exist on disk when you finish.

Write your audit to PROPOSAL.md with:

## Summary
One-paragraph overview of workflow health across the focus area.

## Workflow Traces
For each workflow examined:
### Workflow: <name>
- **Happy path:** Steps from start to completion
- **Friction points:** Where the experience degrades
- **Dead ends:** Paths that lead nowhere or leave the user stuck
- **Missing feedback:** Points where the user doesn't know what's happening
- **Error handling:** How failures are communicated and recovered from

## Cross-Workflow Issues
Problems that affect multiple workflows (shared components, common patterns).

## Workflow Gaps
Workflows that should exist but don't. User needs that aren't addressed.

## Recommended Improvements
Ordered list of workflow fixes, from highest to lowest user impact.

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
