"""Project scaffolding — generate five-document pattern for new projects."""

from pathlib import Path


CLAUDE_MD = """\
# {project_name} — Claude Code Instructions

## Orientation

Read in this order:
1. **CLAUDE.md** (this file) — tech stack, commands, rules
2. **DESIGN.md** — architecture, data model, design decisions
3. **DECISIONS.md** — architecture decision records (living, git is the audit trail)
4. **ROADMAP.md** — phased plan with deliverables
5. **README.md** — user-facing docs, install, quick start

{project_name} is ... (describe your project in one sentence).

**Current state:** (describe current phase or status)

## Tech Stack

- (list your technologies)

## Commands

```bash
# (list your key commands)
```

## Project Structure

```
(describe directory layout)
```

## Rules

### Constraints

- (list hard constraints, e.g. "no external database servers")

### Design Principles

- (list guiding principles)

## Identifier Conventions

- **ADR-NNN** — Architecture Decision Records. Numbered sequentially, never reused. Header format: `## ADR-NNN: Title` in DECISIONS.md.

## Document Maintenance

Five documents. Keep them accurate — drift compounds across sessions.

| When this happens... | ...update these documents |
|----------------------|--------------------------|
| New decision made | DECISIONS.md (ADR + domain index + count), CLAUDE.md (ADR count) |
| Architecture changed | DESIGN.md |
| Phase status changed | ROADMAP.md |
| Commands changed | README.md |
| Rules or constraints changed | CLAUDE.md |
| Project context or methodology evolves | CONTEXT.md |

At phase boundaries, reconcile all documents for consistency.

### Canonical Homes

Each piece of information lives in one place. Other files reference, not duplicate.

| Information | Canonical home |
|-------------|---------------|
| Tech stack & rules | CLAUDE.md |
| Project context | CONTEXT.md |
| Architecture & data model | DESIGN.md |
| Decision rationale | DECISIONS.md |
| Phase history & plan | ROADMAP.md |

### Per-Session Checklist

1. If you added ADRs → update count in CLAUDE.md and DECISIONS.md header
2. If architecture changed → update DESIGN.md
3. Update last-updated footer on every modified document

### Documentation Rules

- **ADRs are mutable living documents.** Update directly — add, revise, or replace content in place. When substantially revising, add `*Revised: [date], [reason]*` at the section's end. Git history is the audit trail.
- **Section-level change tracking.** When substantially revising a DESIGN.md section or an ADR, add `*Revised: [date], [reason or ADR]*` at the section's end.
- **No duplication across documents.** If information exists in its canonical home, other documents reference it.

### Documentation–Code Transition

1. **Before code exists:** DESIGN.md is the source of truth. Follow it precisely.
2. **When implemented:** Add `**Status: Implemented** — see [code path]` at section top. Code becomes source of truth for details; DESIGN.md remains architectural rationale.
3. **When implementation diverges:** Update DESIGN.md to match actual decisions. It is a living document, not a historical artifact.
4. **Section-level tracking:** When substantially revising, add `*Revised: [date], [reason]*` at section end.

## Key Design Decisions (Summary)

Full rationale in DECISIONS.md. 0 ADRs recorded.

*Last updated: project initialized*
"""

DESIGN_MD = """\
# {project_name} — Design

## Core Concept

(Describe what your project does and the key abstraction.)

## Architecture

### Modules

| Module | Responsibility |
|--------|---------------|
| (module) | (what it does) |

### Data Flow

```
(describe how data moves through the system)
```

## Design Decisions

Full rationale in DECISIONS.md.

*Last updated: project initialized*
"""

DECISIONS_MD = """\
# {project_name} — Decisions

Architecture Decision Records. Mutable living documents — update directly when decisions evolve. When substantially revising an ADR, add `*Revised: [date], [reason]*` at the section's end. Git history serves as the full audit trail.

0 ADRs recorded.

## Domain Index

| ADR | Domain | Summary |
|-----|--------|---------|

---

(Add ADRs below as you make design decisions.)

*Last updated: project initialized*
"""

ROADMAP_MD = """\
# {project_name} — Roadmap

## Phase 1: (Name) — IN PROGRESS

(Describe the first phase and what it proves.)

### Deliverables
- [ ] (first deliverable)

### Phase Gate
(What must be true to move to the next phase?)

---

## Phase 2: (Name)

(Describe the second phase.)

### Features

(List planned features.)

### Phase Gate
(What must be true?)

---

## Deferred / Uncertain

Features discussed but not committed to a phase:

- (feature idea)

*Last updated: project initialized*
"""

CONTEXT_MD = """\
# {project_name} — Context

## What This Project Is

(One paragraph describing the project's purpose and scope.)

## Who It's For

(Target users or audience.)

## Project Methodology

This project is maintained through AI-human collaboration. The documentation volume — CLAUDE.md, CONTEXT.md, DESIGN.md, DECISIONS.md, ROADMAP.md — is intentional: it is the project's institutional memory, enabling continuity across AI context windows where no persistent memory exists. Each document serves a distinct role (instructions, context, architecture, rationale, timeline). Together they allow any new session to understand the full project state without archeological effort.

(Describe the AI-human collaboration model for this project: what decisions does the human make? What does the AI execute? Where is the boundary?)

## Key Constraints

(Non-negotiable constraints: technical, business, time.)

## Current Focus

(What you're working on right now and why.)

## What's Working

(What's already built and functioning.)

## What's Not Working

(Known issues, gaps, pain points.)

## Open Questions

(Things you haven't decided yet.)

*Last updated: project initialized*
"""


TEMPLATES = {
    "CLAUDE.md": CLAUDE_MD,
    "DESIGN.md": DESIGN_MD,
    "DECISIONS.md": DECISIONS_MD,
    "ROADMAP.md": ROADMAP_MD,
    "CONTEXT.md": CONTEXT_MD,
}


def scaffold_docs(project_dir: Path) -> list[str]:
    """Scaffold the five-document pattern into a project directory.

    Only creates files that don't already exist. Returns list of created filenames.
    """
    project_name = project_dir.name

    created = []
    for filename, template in TEMPLATES.items():
        path = project_dir / filename
        if not path.exists():
            content = template.format(project_name=project_name)
            path.write_text(content)
            created.append(filename)

    return created
