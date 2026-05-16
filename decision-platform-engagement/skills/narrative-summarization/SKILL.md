---
name: narrative-summarization
description: AI-generated narrative summaries of complex multi-event histories (customer journeys, case files, claims). Replaces log scrolling for senior operators. Produces markdown with structured sections. Trigger when the user wants to summarize a customer/case/claim history, build an "Activity Digest" feature, or wants the AI to tell a story instead of dump data.
metadata:
  type: pattern
  tags: [ai, ux, summarization]
---

# Narrative summarization — replace log scrolling with structured summaries

## What this solves

Senior operators (Heads of Collections, Compliance Officers, Risk Managers) do not read time-series logs. They want a 60-second briefing across every dimension that matters: what's happening with this customer, how they got here, what's notable, what needs attention.

Generic AI summaries ("This customer is in collections") are useless. The pattern below produces structured, dimensional briefings that pass the senior-operator bar.

## The pattern

### 1. Build a per-entity context payload

For each entity (customer, case, claim), assemble a rich context payload:

- Profile + account
- Channel activity in window (grouped by channel + intent)
- Stage transitions
- AI agent actions
- Strategy decisions
- Compliance gate results (PASS + FAIL split)
- Pending escalations + PTPs
- Active compliance flags
- Champion / challenger strategy assignment

The payload should be ~3-15 KB of structured JSON. Too small → not enough context. Too large → exceeds context window or balloons cost.

### 2. Use a structured system prompt requiring sections

The system prompt should demand a specific markdown structure. Verbatim from the reference engagement:

```
You are producing a structured ACTIVITY DIGEST for one customer's collections
journey. The reader is a senior operator (collections head, compliance officer,
or risk manager) who does NOT want to scroll through time-series logs.

Return strict markdown with EXACTLY these sections, in this order. Use the
section headings verbatim. If a section is genuinely empty for the window,
write 'No activity' rather than omit it:

## Snapshot
One sentence summarizing where the customer is right now (stage, DPD, balance, key flag).

## Profile & Account
1-2 sentences on the customer profile and account that's relevant to the journey.

## Customer Activity in Window
What the customer did, grouped by channel and intent. Cite counts and time spans.

## System Actions
What the orchestrator did: strategy evaluations, outbound actions, stage transitions.

## AI Agent Decisions
What AI agents did and why. Cite confidence levels and rationale excerpts.

## Compliance
Validation notice status. Active flags. Action-gate evaluations passed/blocked.

## Strategy
Which version is assigned, any notable changes within the window.

## Open Items
Pending escalations, active PTPs, validation notice deadlines.

## What Needs Attention
1-4 bullet points of concrete things a human should look at or do.

Rules:
- Use `inline code` for IDs, dollar amounts, and policy/rule names.
- Use **bold** for stage names, urgency levels, and severity words.
- Do NOT invent facts not in the input. Do NOT speculate beyond the data.
- Do NOT include preamble like 'Here is the digest'.
- Keep total length under ~800 words.

After the markdown, on a NEW LINE, output a single JSON object on one line
prefixed with `HIGHLIGHTS_JSON:` containing 2-4 of the most important items as:
{"items":[{"dimension":"compliance|risk|operations|ai|profile","severity":"low|medium|high|critical","text":"one-line summary"}]}
```

### 3. Time window selector

Different operators want different windows. Make it a parameter (`?window=24h|7d|30d|90d|all`). The data fetcher applies the window; the system prompt is the same.

### 4. Extract structured highlights

The `HIGHLIGHTS_JSON:` line lets the UI render alert pills above the prose:

- **Compliance · high:** Active compliance flag SCRA_MILITARY
- **Operations · medium:** 10 pending escalations for a human specialist

Parse it out of the LLM response, render as colored pills, fall back to a deterministic heuristic if the LLM didn't include them.

### 5. Render with proper markdown

Use `react-markdown` + `remark-gfm`. Don't render the markdown as plain text — it looks broken (asterisks, hashes everywhere).

### 6. Fallback path

Always have a fallback for when the LLM is unavailable (rate limited, missing API key, network failure). The fallback is a deterministic structured summary using the same data, with the same section headers, without the prose:

```
## Snapshot
Julie Perkins (CUST-0184) is SEVERE, 90 DPD on auto_loan, $11,752 past due of $47,007.

## Profile & Account
12-year tenure. Risk: 790. Preferred channel: voice.

## Customer Activity in Window
9 channel/intent groupings observed.

[etc.]
```

A degraded summary is better than a crash.

## Model choice

- For depth and adaptive thinking: Claude Opus 4.7 with `thinking: {"type": "adaptive"}`
- For volume / cheaper: Claude Sonnet 4.6 or Haiku 4.5
- For local/sovereign: any modern LLM with > 32k context window

The system prompt is portable.

## Caching strategy

Cache the digest per (entity_id, window) with a TTL of 60-120 seconds. The data changes second-by-second but the summary doesn't need to.

## Cost note

Each digest call costs ~$0.05-0.15 in tokens (Opus 4.7). Track per-customer per-day digest count via the cost dashboard (see `cost-observability` skill). Cap at e.g. 10 digests/customer/day to prevent runaway spend from a curious operator hitting refresh.

## Common failure modes to avoid

- **Free-form prompt without structure.** "Summarize this customer" → unpredictable output, no UI parseable structure.
- **Plain text rendering.** Markdown is wasted if you render as plain text.
- **No fallback.** First time the LLM is down, the UI breaks.
- **Letting the LLM invent.** If the data doesn't say it, the summary shouldn't say it. The system prompt must say "Do NOT speculate beyond the data."
- **No window selector.** A senior operator may want 24h for triage and 90d for case review — same prompt, different data slice.

## Worked example from the reference engagement

`/api/story/customers/{id}/activity-digest?window=7d` builds the context payload from Postgres + the lakehouse, sends it to Claude Opus 4.7 with the system prompt above, returns the markdown summary + highlights + token count + model used.

The Customer Story page renders the digest with a window picker (24h / 7d / 30d / 90d / all), severity-coloured highlight pills at the top, full markdown body, and a context footer showing exactly what data was synthesized.

Stakeholder reaction: "This replaces the case-management screen the supervisor uses today."
