---
name: stakeholder-driven-ui
description: One UI surface per stakeholder persona, each designed to answer that persona's first ten questions. No single dashboard tries to serve everyone. Trigger when the user is designing UIs, picking what pages to build, or asking "who is this for".
metadata:
  type: pattern
  tags: [ui, design, stakeholder]
---

# One UI surface per persona

## What this solves

A single dashboard cannot serve a CRO and a Head of Collections and a CCO — their first ten questions are different. A "kitchen sink" page becomes a generic feature list that nobody loves.

Designing one surface per persona means each stakeholder walks out repeating their own one-liner — and that's the demo working.

## The pattern

### 1. Enumerate the personas

Pull from `docs/stakeholder-archetypes.md`. Typical scope:
- Head of Operations (COO)
- Case investigator (Compliance, Audit)
- CRO / Risk
- CCO / Legal
- CTO / Platform
- CDO / Data
- SRE
- AI / ML lead

### 2. For each persona, design one landing surface

Each surface is the answer to "what do I open first when I sit down at this platform?"

| Persona | Landing surface | Their first 10 questions belong here |
|---|---|---|
| COO / Head of Operations | Operations Floor | live portfolio, channel activity, queue depth, escalations |
| Case Investigator / Compliance | Customer Story | narrative summary, timeline, audit trail per case |
| CRO | Risk & ML | model card, scoring, roll-rate forecast, A/B significance |
| CCO | Strategy Console + Compliance audit | live policy evaluations, blocks, validation notices |
| CTO / SRE | Platform Operations | service heartbeats, Kafka topology, OPA decision feed, traces |
| CDO | Data Lakehouse | medallion topology, lineage, ad-hoc SQL |
| AI/ML lead | AI Explorer | live auto-fired agent activity + manual playground |

### 3. Each surface optimizes for "first impression"

The first thing the persona sees should answer their #1 question. For:
- **COO:** Are we operating? (pulse strip — events/min, active journeys, escalations)
- **CRO:** Is the model working? (model status badge — AUC, training rows)
- **CCO:** Are we compliant? (compliance enforcement metric: blocked / allowed)
- **CTO:** Is the platform alive? (service status — 3/3 healthy, lag = 0)
- **CDO:** Is data flowing? (medallion topology with object counts)

The rest of the page can go into detail — but the top 200 pixels deliver the headline.

### 4. Cross-link aggressively

A surface designed for one persona will be visited by others. Make cross-links obvious. From the Customer Story page, link to:
- Platform Ops trace viewer (for the CTO who walked over)
- Risk & ML score (for the CRO who's curious about this customer)
- Strategy Console (to see the policies that fired)

Every clickable element should consider "if a different persona clicks this, where do they expect to land?"

### 5. Don't try to fit everything on one page

Resist the temptation to add an "audit panel" to the Operations Floor because the auditor might also be in the room. The audit panel belongs on the Customer Story page or the Strategy Console. Cross-link to it.

## Page composition principles

For each surface:

- **Pulse strip at top** — 4-6 high-level numbers, each updated live (5-10 second refresh interval)
- **Live feeds** — recent activity in chronological order, drill-down on click
- **Comparison panels** — A/B, before/after, segment vs segment
- **Detail tables** — full row data for power-user inspection
- **Drill links** — every entity (customer_id, agent_action_id, event_id) is clickable into the appropriate detail page

## Stylistic notes

- Color-code by domain consistently across pages (compliance = emerald, AI = purple, decisions = amber, lakehouse = slate, risk = indigo)
- Use a single typography scale; no random sizes
- Status badges (healthy / warn / bad) should look identical on every page
- Avoid raw JSON as the primary view; collapse it into details summaries
- Use markdown rendering for any AI-generated text (see `narrative-summarization` skill)

## Anti-patterns to reject

- **Tabbed all-in-one dashboards.** "Operations" tab, "Compliance" tab, "Risk" tab on the same URL is the same as no design — it just gives every persona a slow scroll.
- **Configuration-heavy first surfaces.** If a stakeholder needs to set filters before the page tells them anything, the design is wrong.
- **JSON textareas.** A textarea with an Evaluate button is a developer toy, not a stakeholder surface.
- **Generic "dashboard" branding.** Name each surface for what it does ("Operations Floor", "Customer Story", "Risk & ML"). Generic names create generic mental models.

## Tooling

For React projects:
- Tanstack Query for live data with auto-refresh
- Lucide React for consistent iconography
- Tailwind for design system enforcement
- `react-markdown` for AI text

## Worked example from the reference engagement

Eight UI surfaces, one per persona:

| Surface | Persona | First-impression metric |
|---|---|---|
| Operations Floor | COO | 88 active journeys, 110 events/min |
| Customer Story | Investigator / CCO | AI-generated narrative summary |
| AI Explorer | AI/ML lead | Live auto-fired agent counts per agent |
| Strategy Console | CRO / CCO | Champion vs Challenger comparison cards |
| Platform Operations | CTO / SRE | 3/3 services healthy + Kafka topology |
| Data Lakehouse | CDO | Medallion topology with S3 bucket names |
| Risk & ML | CRO + data science | Risk model AUC + feature importance |
| Scenarios | Demo operator | Pre-scripted demo paths |

Each persona walks straight to their surface. Each surface answers the first 10 questions. Cross-links handle the rest.
