"""Claude Code skill scaffolding — generate project-specific skills from docs."""

from pathlib import Path


# --- Detection signals ---

SIGNALS = {
    "mission-align": [
        "mission", "principle", "constraint", "value", "tenet",
        "non-negotiable", "core belief", "guiding",
    ],
    "cultural-lens": [
        "language", "i18n", "multilingual", "translation", "locale",
        "internationalization", "l10n", "cultural", "globalization",
    ],
    "persona-ux": [
        "persona", "user journey", "seeker", "reader", "visitor",
        "customer", "end user", "target audience", "user story",
    ],
    "compliance-check": [
        "compliance", "gdpr", "privacy", "hipaa", "sox", "pci",
        "regulation", "data protection", "consent", "audit trail",
    ],
}


# --- Skill templates ---

SKILL_MISSION_ALIGN = """\
---
name: mission-align
description: "{project_name} principle alignment check. Verifies designs honor stated project principles and constraints."
argument-hint: "[optional principle to focus on]"
---

Read CLAUDE.md, DESIGN.md, DECISIONS.md, and ROADMAP.md to ground in the project's actual state.

## Mission Alignment Check

Audit against the project's stated principles and constraints.

For each principle or constraint documented in the project:
1. Is the current design faithful to it?
2. Are there areas where it's at risk of being violated?
3. Are there implicit violations that aren't obvious?

Focus area: $ARGUMENTS

For every misalignment or risk:
1. What principle is at risk and how
2. Where the issue is (file, section, identifier)
3. The specific change to restore alignment

Present as an action list. No changes to files — document only.

What questions would I benefit from asking?

What am I not asking?
"""

SKILL_CULTURAL_LENS = """\
---
name: cultural-lens
description: "Inhabit a specific cultural, demographic, or contextual perspective and audit the design for sensitivity, inclusion, accessibility, and blind spots."
argument-hint: "[culture, perspective, or demographic]"
---

Read CLAUDE.md, DESIGN.md, DECISIONS.md, and ROADMAP.md to ground in the project's actual state.

## Cultural Perspective Audit

Inhabit the perspective of: $ARGUMENTS

From this perspective:

1. **Language & communication** — Does the project communicate naturally and respectfully? Are translations adequate? Is the tone culturally appropriate?
2. **Visual & interaction design** — Do the design choices feel welcoming or alien? Cultural associations of colors, symbols, layouts?
3. **Technical access** — Can this person actually use the product? Device availability, bandwidth constraints, data costs, browser diversity.
4. **Content relevance** — Which content has particular resonance? Which might need additional context?
5. **Assumptions examined** — What does the current design assume about the user that may not hold for this perspective?
6. **What uplifts?** — What simple touches would make this person feel welcomed and served?
7. **What alienates?** — What might feel exclusionary, insensitive, or simply confusing?

For every finding:
1. The specific concern or opportunity
2. Where it manifests (design element, content decision, UX flow)
3. The proposed change or consideration

Present as an action list. No changes to files — document only.

What questions would I benefit from asking?

What am I not asking?
"""

SKILL_PERSONA_UX = """\
---
name: persona-ux
description: "User experience review from a specific persona's perspective. Evaluates accessibility, discoverability, delight, and friction points."
argument-hint: "[persona or scenario to focus on]"
---

Read CLAUDE.md, DESIGN.md, DECISIONS.md, and ROADMAP.md to ground in the project's actual state.

## Persona Experience Review

Evaluate the experience from the perspective of: $ARGUMENTS

1. **First encounter** — What does a new user experience? Is the entry point clear, welcoming, non-overwhelming?
2. **Core workflow** — Is the primary workflow smooth? Where is there friction?
3. **Discoverability** — Can the user find what they need? Are there multiple paths to the same goal?
4. **Accessibility** — Screen readers, keyboard navigation, reduced motion, touch targets. Experience on low-end devices?
5. **Error states** — What happens when things go wrong? Are errors helpful or cryptic?
6. **Delight** — What simple touches make the experience feel crafted rather than generic?
7. **Return visits** — What brings someone back? What state is preserved?

For every insight:
1. The UX finding (friction, opportunity, or strength)
2. Where it manifests
3. The proposed improvement

Present as an action list. No changes to files — document only.

What questions would I benefit from asking?

What am I not asking?
"""

SKILL_COMPLIANCE_CHECK = """\
---
name: compliance-check
description: "Regulatory and policy compliance review. Checks data handling, privacy, consent, audit trails, and stated compliance requirements."
argument-hint: "[optional regulation or area to focus on]"
---

Read CLAUDE.md, DESIGN.md, DECISIONS.md, and ROADMAP.md to ground in the project's actual state.

## Compliance Review

Audit against stated compliance requirements and general best practices:

1. **Data handling** — What data is collected, stored, and transmitted? Is it minimized? Are retention policies defined?
2. **Privacy** — Is user identification minimized? Are tracking and profiling practices documented and justified?
3. **Consent** — Where is user consent required? Is it collected correctly? Can it be withdrawn?
4. **Audit trails** — Are significant actions logged? Can compliance be demonstrated to auditors?
5. **Access control** — Who can access what data? Are permissions principle-of-least-privilege?
6. **Third-party risk** — What external services handle user data? Are DPAs in place?
7. **Incident response** — Is there a plan for data breaches or compliance violations?

Focus area: $ARGUMENTS

For every finding:
1. The compliance risk or gap
2. Where it exists (code, design, policy, or missing entirely)
3. The specific remediation

Present as an action list. No changes to files — document only.

What questions would I benefit from asking?

What am I not asking?
"""


SKILL_TEMPLATES = {
    "mission-align": SKILL_MISSION_ALIGN,
    "cultural-lens": SKILL_CULTURAL_LENS,
    "persona-ux": SKILL_PERSONA_UX,
    "compliance-check": SKILL_COMPLIANCE_CHECK,
}


def _read_project_docs(project_dir: Path) -> str:
    """Read project documentation into a single string for signal detection."""
    doc_names = ["CLAUDE.md", "DESIGN.md", "CONTEXT.md", "ROADMAP.md", "DECISIONS.md"]
    parts = []
    for name in doc_names:
        path = project_dir / name
        if path.exists():
            try:
                parts.append(path.read_text())
            except OSError:
                pass
    return "\n".join(parts)


def detect_skills(project_dir: Path) -> dict[str, bool]:
    """Detect which project-specific skills would be relevant.

    Returns a dict of skill_name -> detected (True/False).
    """
    docs_text = _read_project_docs(project_dir).lower()

    results = {}
    for skill_name, keywords in SIGNALS.items():
        results[skill_name] = any(kw in docs_text for kw in keywords)

    return results


def scaffold_skills(project_dir: Path) -> list[str]:
    """Scaffold Claude Code skills into .claude/skills/.

    Only creates skills that:
    1. Have signals detected in project docs
    2. Don't already exist in .claude/skills/

    Returns list of created skill names.
    """
    claude_dir = project_dir / ".claude"
    skills_dir = claude_dir / "skills"

    detected = detect_skills(project_dir)
    project_name = project_dir.name

    created = []
    for skill_name, was_detected in detected.items():
        if not was_detected:
            continue

        skill_dir = skills_dir / skill_name
        skill_file = skill_dir / "SKILL.md"

        if skill_file.exists():
            continue

        template = SKILL_TEMPLATES.get(skill_name)
        if template is None:
            continue

        content = template.format(project_name=project_name)

        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(content)
        created.append(skill_name)

    return created
