---
name: engagement-demo-flow
description: Generate an N-stop demo flow tailored to the engagement profile, with persona tags and one-liner scripts per stop.
---

# /engagement-demo-flow

You are producing a **demo flow** — an ordered, time-budgeted, persona-tagged walkthrough of the platform that hands each stakeholder their first ten questions.

## Pre-requisites

Read in order:
1. `docs/engagement-profile.md` (who's in the room, demo time budget, audience format)
2. `docs/capability-matrix.md` (what to emphasize)
3. `docs/stakeholder-archetypes.md` in this plugin (one-liners each persona should walk out repeating)

## Demo budget calibration

| Audience format | Typical budget | # of stops |
|---|---|---|
| 1-on-1 executive briefing | 12-15 min | 6-8 stops |
| Architecture review (5-15 people) | 20-30 min | 8-10 stops |
| Steering committee | 30-45 min | 10-12 stops |
| Board presentation | 10-15 min (high signal) | 5-7 stops |
| Public conference / showcase | 15-20 min | 7-9 stops |

Pick a budget from the engagement profile or ask the user.

## Building the flow

### 1. Start with the highest-impact opener

The opener establishes "this is real, not a slide." Typical openers:

- **Live operations view** (Operations Floor for collections, claims queue for insurance, transaction feed for fraud)
- **Why pick this one?** Because it shows the platform alive without anyone touching it. Sets the tone.

### 2. Walk into one specific case

After the bird's-eye opener, drill into one specific case (one customer, one claim, one transaction). The Customer Story / Case Story page tells the entire narrative in 60-90 seconds via the AI-generated summary.

### 3. Show governed AI

Third stop is the AI Explorer / Agent Workbench. Show that AI is not a black box: structured decisions, calibrated confidence, persisted reasoning trace.

### 4. Strategy / policy

Fourth stop is the Strategy Console or equivalent. Show the policy engine, the A/B framework, the live audit feed. This is the CRO + CCO stop.

### 5. The lakehouse + lineage proof

Fifth stop is the Data Lakehouse with end-to-end lineage. This is the CTO + CDO stop. The lineage flow converts skepticism into excitement.

### 6. Platform operations

Sixth stop is the SRE-facing observability view. Show services, Kafka, OPA, traces. Confirms the platform is real, not vaporware.

### 7. Risk & ML

Seventh stop is the Risk & ML page. Show the model card, A/B significance, cost dashboard. This is the second CRO stop and the FinOps stop.

### 8. The WORM closer

Last stop is the audit demo. Open a SQL prompt, try to UPDATE / DELETE an audit row, watch the trigger raise. This sends the audit / SOX / SOC 2 stakeholder out smiling.

## Adapting to the room

- **Heavy CTO / SRE crowd:** spend more time on Platform Ops and Lakehouse; compress the operations + customer-story sections.
- **Heavy CRO / CCO crowd:** spend more time on Strategy Console + Risk/ML; compress the lakehouse section to just the lineage proof.
- **Heavy COO / operations crowd:** spend more time on Operations Floor + Customer Story; compress everything else.
- **Mixed C-suite + audit:** keep the canonical 8-stop flow; this is the sweet spot.

## Output format

Write to `docs/demo-flow.md`:

```markdown
# Demo flow — <engagement name>

**Audience:** <from profile>
**Duration:** N minutes
**Number of stops:** M

## Stop 1 · <Surface name> · <duration>

**Persona tags:** [CTO] [CRO] [CCO]
**Goal of this stop:** <what the stakeholder should conclude>

**Script:**
> "<one-line opener>"
> Click → <UI action>
> Show → <what's on screen>
> Conclude → <one-liner the stakeholder repeats>

---

## Stop 2 …

```

For each stop, include the **one-liner the stakeholder should walk out repeating** — that's the test of whether the stop landed.

## Output guarantees

- `docs/demo-flow.md` exists with M stops
- Each stop has persona tags, duration, script, and a "walk-out one-liner"
- Total duration sums to the target budget

## What to do next

Run `/engagement-brief` to produce the stakeholder leave-behind HTML.
