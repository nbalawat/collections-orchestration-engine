---
name: data-lineage-ui
description: A UI feature where any event_id can be traced across every storage tier — Kafka, OLTP, pub/sub, bronze object store, silver Parquet, gold marts. Proves the architecture is real by showing it. Trigger when the user mentions data lineage, end-to-end trace, "prove the architecture", correlation IDs, audit chain, or "how do we know the data flows correctly".
metadata:
  type: pattern
  tags: [observability, lakehouse, audit, demo-impact]
---

# Data lineage as a UI feature

## What this solves

A great architecture diagram is a slide. Real data lineage is a button. Building a single endpoint that walks an event_id through every storage tier — and a UI that renders it as a horizontal flow — converts skeptical CTO/CDO conversations into excited ones in under 30 seconds.

This is the highest-leverage technical UX feature you can build for a stakeholder demo.

## The pattern

### 1. Propagate correlation IDs end-to-end

Every inbound event seeds a `correlation_id` (a UUID). It rides on:

- Kafka headers (or the event payload — pick one and stick to it)
- The Temporal workflow's internal state
- Every downstream event the workflow emits (decisions, actions, compliance, lifecycle, ai_reasoning)
- Every database row written as a result
- Every audit table entry

The fundamental contract: **same business event → same correlation_id, everywhere it appears.**

### 2. Build a /api/lineage/{event_id} endpoint

For a given event_id, walk every tier:

| Tier | What to surface |
|---|---|
| **Kafka** | Topic name, message key, partition count, retention |
| **Postgres** | Table name, primary key, the full row, WORM status badge, trigger note |
| **Redis** | Pub/sub channels, purpose, TTL |
| **Bronze (S3)** | Exact gzipped object key, line number within file, file size, the raw record JSON |
| **Silver (S3)** | Partition pattern, the Parquet row pulled via DuckDB |
| **Gold (marts)** | Which marts include this event and which columns it bumps (computed contributions) |
| **Downstream** | Other events / agent actions / escalations sharing the correlation_id |

The hardest part is the Bronze hop: walk the right partition (`topic=<t>/date=YYYY-MM-DD/hour=HH/`), download each `.jsonl.gz` object, decompress, scan for the matching `event_id`. Surface line number.

### 3. Build the UI as a horizontal flow

Render the result as horizontal cards (stations), arrows between them labeled with the mechanism that moves data:

```
Kafka  ──signal-bridge──►  Postgres  ──Redis pub/sub──►  Bronze  ──compactor──►  Silver  ──gold-builder──►  Gold
```

Each card shows: tier name, location (s3 key / table / channel), found-status badge, expandable JSON of the actual data at that hop.

### 4. Add suggestion chips

Pulling lineage cold is hard — the user has to know an event_id. Add a `/api/lineage-suggestions` endpoint that returns the 10 most recent events with rich downstream activity (correlation_id present + linked agent_actions). Render them as clickable chips above the input.

### 5. Show the downstream

Below the six tier cards, show:
- Related events sharing the correlation_id
- AI agent actions on the same trace
- Escalations triggered

This converts "trace one event" into "trace a business outcome."

## Why this is so impactful

| Stakeholder | Reaction to the lineage feature |
|---|---|
| CTO | "OK, the architecture is actually real." |
| CDO | "Lineage is a button, not a slide." |
| Audit / SOX | "Evidence collection is a single API call." |
| SRE | "Debugging just became a SELECT." |

You can rehearse the demo and time this stop — it takes 30 seconds to deliver and changes the energy of the room.

## Performance considerations

- The Bronze scan is the slow part (downloads + decompresses up to ~50 objects). Cache the result for repeated lookups of the same event_id.
- Use `list_objects_v2` with the most specific prefix possible (`topic=X/date=Y/hour=Z/`).
- For high-volume production, materialize a `lineage_index` table that maps event_id → bronze_key + line_offset.

## Common failure modes to avoid

- **No correlation_id propagation.** If correlation IDs only exist in some hops, lineage is partial → not credible.
- **Mapping by customer_id instead of correlation_id.** A customer has hundreds of events; correlation_id is the right key.
- **Skipping the raw data view.** Show the actual JSON. Stakeholders need to see real content, not abstracted summaries.
- **Slow Bronze scan with no progress indicator.** Lineage that takes 30+ seconds to return loses the moment.

## Worked example from the reference engagement

`/api/lakehouse/lineage/{event_id}` returns a structured payload with all six tier hops + downstream. The `/lakehouse` UI page renders this as a horizontal stations flow. Found-status checkmarks per tier; expandable JSON for Postgres row, Bronze raw record, Silver Parquet row.

For the demo: click a recent event chip, watch the trace render in ~3 seconds, then click into the Bronze JSON details to show "this exact event sits at line 1 of 6 in this exact gzipped S3 object". The room goes quiet for a second, then someone asks "wait, that's actually pulling from S3 right now?"
