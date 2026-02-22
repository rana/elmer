# Continual Improvement Audits

Repeatable audit archetypes for elmer. Each archetype yields fresh value after every iteration of project changes. Run them individually, in batch, or via the daemon.

## Audit Archetypes

| Archetype | Purpose | `$TOPIC` is... |
|-----------|---------|-----------------|
| `consistency-audit` | Subsystem consistency & reasoning sufficiency | A subsystem name (e.g., "data model", "CLI interface") |
| `coherence-audit` | Cross-reference integrity across all docs | Optional focus area, or leave broad |
| `architecture-audit` | Pattern compliance, drift, emerging patterns | A component or layer (e.g., "API layer", "state management") |
| `operational-audit` | Ops readiness, cost, resilience, scaling | A deployment concern (e.g., "error recovery", "cost at scale") |
| `documentation-audit` | Doc practice quality, staleness, onboarding | Optional focus area, or leave broad |
| `opportunity-scan` | Emergent opportunities, hidden simplifications | Optional theme, or leave open-ended |
| `workflow-audit` | End-to-end workflow tracing for friction/gaps | Workflow names (e.g., "new user onboarding", "CI pipeline") |
| `mission-audit` | Alignment with stated principles and values | Optional principle to focus on, or audit all |

## How to Use

### Single audit

```bash
elmer explore "data model" -a consistency-audit
elmer explore "API layer" -a architecture-audit
elmer explore "" -a opportunity-scan
```

### Batch audit

Create a topics file, one per line:

```
# topics-consistency.txt
data model
CLI interface
configuration system
state management
worker orchestration
```

```bash
elmer explore -f topics-consistency.txt -a consistency-audit
```

### With AI enhancements

```bash
# AI picks the best archetype for each topic
elmer explore "state management" --auto-archetype

# AI generates a richer prompt from the archetype
elmer explore "data model" -a consistency-audit --generate-prompt

# Auto-review when done (no human gate)
elmer explore "API layer" -a architecture-audit --auto-approve
```

### Via daemon

The daemon can cycle through audits automatically:

```bash
elmer daemon --auto-approve --generate --interval 600
```

## Recommended Cadence

| Frequency | Archetypes |
|-----------|-----------|
| After every significant change | `consistency-audit` (one subsystem per run), `coherence-audit` |
| Weekly or per-phase | `architecture-audit`, `operational-audit`, `workflow-audit`, `documentation-audit` |
| Per release or milestone | `mission-audit`, `opportunity-scan`, `operational-audit` |

### Cycling through subsystems

For `consistency-audit`, cycle through your project's subsystems across runs rather than auditing everything at once. Identify your subsystems (they'll be project-specific) and rotate:

```bash
# Run 1
elmer explore "data model" -a consistency-audit
# Run 2
elmer explore "CLI interface" -a consistency-audit
# Run 3
elmer explore "worker orchestration" -a consistency-audit
```

## What Was Dropped

The original document (from srf-yogananda-teachings) contained domain-specific audits that don't generalize to all projects:

- **Cultural Perspective Audit** — i18n/cultural sensitivity checks for multilingual web projects
- **Multilingual Readiness Check** — language support verification
- **Verbatim Fidelity Audit** — source text accuracy for content projects
- **Global Equity & Accessibility Audit** — web accessibility (WCAG) and low-bandwidth concerns

These are valid audit angles for specific project types. If your project needs them, create project-local archetypes in `.elmer/archetypes/` — elmer checks that directory first before falling back to bundled archetypes.

## Creating Project-Specific Audit Archetypes

Any `.md` file in `.elmer/archetypes/` becomes available as an archetype. Use `$TOPIC` for the substitution point. Follow the pattern of the bundled archetypes:

1. Opening line: archetype purpose
2. Doc-reading boilerplate (CLAUDE.md, DESIGN.md, etc.)
3. `$TOPIC` marker
4. Specific audit questions and methodology
5. PROPOSAL.md output format with structured sections
