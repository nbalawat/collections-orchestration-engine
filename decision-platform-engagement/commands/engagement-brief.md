---
name: engagement-brief
description: Generate a self-contained stakeholder brief HTML — the leave-behind document for executive and architecture review.
---

# /engagement-brief

You are producing a **self-contained HTML brief** — the leave-behind document senior stakeholders will email, print, share, and reference for weeks after the meeting. Inline CSS, no external dependencies, print-friendly.

## Pre-requisites

Read:
- `docs/engagement-profile.md` (stakeholders, regulatory frame, deliverable form)
- `docs/capability-matrix.md` (what to highlight)
- `docs/demo-flow.md` (what's in the demo)
- `templates/stakeholder-brief.html` in this plugin (parameterized template)

## Sections to include

Use the structure from `templates/stakeholder-brief.html`. Eight sections:

1. **Hero** — title, tagline, badges naming the tech stack and regulatory frame
2. **Executive Summary** — what the platform is, why it matters, four commitments
3. **Architecture** — ASCII diagram showing the event flow
4. **Capabilities** — 8 capability cards, each with proof point
5. **Stakeholder Takeaways** — one card per stakeholder in scope (from engagement profile)
6. **Proof Matrix** — capability × concern × persona × proof number (from capability-matrix.md)
7. **Demo Flow** — N-stop walkthrough (from demo-flow.md)
8. **Roadmap** — 3-horizon (4 weeks / 3 months / 9 months)

## Tailoring the brief

The template is parameterized. For each section, **populate from the engagement profile**:

| Template placeholder | Source |
|---|---|
| `<title>` | engagement-profile.md → industry + problem |
| Tagline | engagement-profile.md → demo buyer's frame |
| Hero badges | engagement-profile.md → stack + regulatory frame |
| Capability cards | only include capabilities that exist in this engagement |
| Stakeholder cards | one per persona in scope (from engagement profile) |
| Proof matrix rows | from capability-matrix.md |
| Demo flow stops | from demo-flow.md |
| Roadmap content | generate based on what's already built vs what's in the backlog |

## Don't include capabilities you haven't built

A common failure mode: copying capability cards verbatim from the reference engagement when this engagement hasn't built that capability yet. The brief becomes a wishlist instead of a record. Drop any card whose capability isn't real in *this* engagement, or move it to the roadmap section.

## Output

Write to `docs/stakeholder-brief.html` in the current working directory.

After writing, verify:
- File is self-contained (no `<link>`, no `<script src=>` to external URLs)
- Renders in a browser without errors
- Print preview looks clean (the template includes print media queries)

## Stylistic notes

- Inline CSS in `<style>` block
- System fonts only (no Google Fonts)
- Color scheme: dark slate for headers (#0f172a), indigo accent (#4f46e5), subtle gradient backgrounds
- Each capability card gets a colored accent bar matching the domain (blue for orchestration, amber for policy, purple for AI, emerald for compliance, slate for lakehouse, indigo for risk/ML)
- Each stakeholder card includes a role chip, three takeaways, what to look at, and the one-liner they'll repeat

## Output guarantees

- `docs/stakeholder-brief.html` exists
- Opens in any browser as a self-contained document
- All sections present and populated from real engagement data (not template placeholders)
- Print-friendly

## What to do next

The brief is the natural last step before the demo. After this, the user might want:
- `/engagement-roadmap` if not yet produced — companion document for the post-demo conversation
- Tag the codebase at the current state for reproducibility
